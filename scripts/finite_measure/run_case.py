"""One bounded real-owner finite-observation case, no installs or fake backend.

python scripts/finite_measure/run_case.py --output /absolute/new/output
Exit 0: all native steps and cold checks passed; 2: native NOT_RUN (not installed),
while the real Data/Plan/save/cold prefix has its own checks; 1: actual failure.
Never reuse an existing output folder or change any user-owned session.
"""
from __future__ import annotations
from copy import deepcopy
from pathlib import Path
import argparse, importlib.util, json, os, shutil, subprocess, sys, time, traceback, uuid
ROOT=Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:sys.path.insert(0,str(ROOT))
from caelab.workbench import Workbench
from caelab.contracts import CapabilityUnavailable
from caelab.storage import canonical_hash
from caelab.data_material_service import DataMaterialService
from caelab.finite_measure_input import mapping,recipe,verify_import
from caelab.finite_measure_protocol import recipe as driver_recipe
from caelab.finite_measure_prediction import comparison_extension,derive
from caelab.material_test import measured_protocol,physical_residual
from caelab.numerical_document import from_material_document
from caelab.numerical_candidate_detail import plain,table_rows
from caelab.numerical_candidate_evidence import CAPTURE,SUCCESS,resolve_candidate_evidence,compare_selected_candidate_evidence


def save(path, value):
    Path(path).write_text(json.dumps(plain(value),ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')


def command(w,document,operation,arguments=None,**overrides):
    if isinstance(document,str):document=w.document_read(document)
    return w.document_command(document['id'],operation,arguments or {},session_id=document['session_id'],
        expected_generation=document['generation'],**overrides)


def wait(w,job,timeout=120):
    identifier=job['id'] if isinstance(job,dict) else job
    deadline=time.monotonic()+timeout
    while time.monotonic()<deadline:
        status=w.manager.status(identifier)
        if status['state'] in ('SUCCEEDED','FAILED','REJECTED','CANCELLED'):
            if status['state']!='SUCCEEDED':raise AssertionError(status)
            return w.result(identifier)
        time.sleep(.04)
    # The task is ours; do not kill unrelated sessions/processes.
    w.manager.cancel(identifier)
    raise TimeoutError('Own job did not finish: '+identifier)


def import_case(w,output,tag):
    fixture=ROOT/'examples/finite-measure';config=json.loads((fixture/(tag+'-config.json')).read_text())
    receipt=w.upload(tag+'.csv',(fixture/(tag+'.csv')).read_bytes())
    d=w.document_open(kind='data',title='유한변형 '+tag,draft={'data_id':receipt['id'],
        'mapping':mapping(config),'finite_measure':config})
    assert not d['diagnostics'],d['diagnostics']
    job=command(w,d,'data.import')['job'];imported=wait(w,job)
    verify_import(config,imported)
    d=w.document_read(d['id']);run=d['runs'][-1]
    source={k:run[k] for k in ('job_id','input_revision','input_sha256')};source['document_id']=d['id']
    draft=deepcopy(d['draft']);draft['processing']={'source':source,'recipe':recipe(config)}
    d=command(w,d,'data.update',{'draft':draft})['document']
    preview=w.data_documents.processing_preview(d['id'])
    assert preview['execution_status']=='SUCCEEDED',preview['stages']
    applied=command(w,d,'data.processing.apply',{'preview_sha256':preview['preview_sha256']})
    rev=applied['processing']['id'];d=command(w,applied['document'],'document.save')['document']
    result=w.data_documents.processing_result(d['id'],rev,selection=['finite_sigma','finite_lambda'])
    oracle=json.loads((fixture/(tag+'-oracle.json')).read_text())
    for got,expected in zip(result['responses']['finite_sigma']['value'],oracle):assert abs(got-expected['sigma'])<1e-11
    save(output/(tag+'-processing-audit.json'),result)
    return dict(document_id=d['id'],processing_revision=rev,source=source,
        result=result,result_hash=canonical_hash(result),immutable_hash=immutable_processing_hash(result),
        stored_result_sha256=result['diagnostics']['processing_record']['result_sha256'],
        draft_hash=canonical_hash(d['draft']),raw_job=job['id'],
        raw_result_hash=canonical_hash(w.document_result(d['id'],job['id'])))


def immutable_processing_hash(result):
    value=deepcopy(result)
    # Retained revision is a current storage locator, not part of saved result.json.
    value['diagnostics']['processing_record'].pop('retained_revision',None)
    return canonical_hash(value)


def read_cold(output):
    record=json.loads((output/'checkpoint.json').read_text(encoding='utf-8'))
    w=Workbench(output/'store',configuration={'workers':1,'cpu_budget':1})
    try:
        before=len(w.manager.list())
        for item in record['data']:
            doc=w.document_open(kind='data',document_id=item['document_id'])
            assert canonical_hash(doc['draft'])==item['draft_hash']
            result=w.data_documents.processing_result(doc['id'],item['processing_revision'],selection=['finite_sigma','finite_lambda'])
            assert canonical_hash(result)==item['result_hash']
            assert result['diagnostics']['processing_record']['result_sha256']==item['stored_result_sha256']
            assert canonical_hash(w.document_result(doc['id'],item['raw_job']))==item['raw_result_hash']
        plan=w.document_open(kind='numerical',document_id=record['plan_id'])
        material=w.document_open(kind='material',document_id=record['material_id'])
        assert canonical_hash(plan['draft'])==record['plan_hash']
        assert canonical_hash(material['draft'])==record['material_hash']
        canonical=w.numerical_documents.job_arguments(plan['draft'])
        assert canonical_hash(canonical['frozen_inclusion'])==record['frozen_hash']
        if record.get('fit_job'):
            assert canonical_hash(w.document_result(plan['id'],record['fit_job']))==record['fit_hash']
            for reference in record['evidence']:
                resolved=resolve_candidate_evidence(w.numerical_documents,reference,consumer='adoption')
                assert resolved['readiness']['success_judgment_permitted']
                w.numerical_candidate_detail(plan['id'],record['fit_job'],reference['candidate_id'],attempt_job_id=reference['attempt_job_id'])
        assert len(w.manager.list())==before,'Cold read must not create jobs'
        # Literal incomplete text is saved/reopened in current owner; it does not
        # rewrite any past processing result or the frozen Plan source.
        first=w.document_read(record['data'][0]['document_id']);draft=deepcopy(first['draft'])
        draft['finite_measure']['geometry']['L0']['value']='1e'
        draft['processing']['recipe']=recipe(draft['finite_measure'])
        first=command(w,first,'data.update',{'draft':draft})['document']
        first=command(w,first,'document.save')['document']
        assert first['draft']['finite_measure']['geometry']['L0']['value']=='1e'
        bad_preview=w.data_documents.processing_preview(first['id'])
        assert 'finite_sigma' not in bad_preview['responses'] and 'finite_lambda' not in bad_preview['responses']
        assert not any(bad_preview['channels']['finite_lambda']['operation_valid'])
        assert all(bad_preview['channels']['finite_lambda']['operation_reasons'])
        assert immutable_processing_hash(w.data_documents.processing_result(first['id'],record['data'][0]['processing_revision'],
            selection=['finite_sigma','finite_lambda']))==record['data'][0]['immutable_hash']
        draft['finite_measure']['geometry']['L0']['value']=50.;draft['processing']['recipe']=recipe(draft['finite_measure'])
        first=command(w,first,'data.update',{'draft':draft})['document'];command(w,first,'document.save')
        save(output/'cold.json',{'state':'PASS','new_process_pid':os.getpid(),'jobs_created':len(w.manager.list())-before,
            'raw_invalid_text_save_and_correct':'PASS','historical_hashes':'UNCHANGED'})
    finally:assert w.shutdown()['joined']


def run(output):
    output.mkdir(parents=True,exist_ok=False)
    case=json.loads((ROOT/'examples/finite-measure/FIXED_CASE.json').read_text())
    save(output/'fixed-before-run.json',case)
    w=Workbench(output/'store',configuration={'workers':1,'cpu_budget':1})
    record={'data':[],'status':'RUNNING','environment':{'python':sys.version,'platform':sys.platform,'pid':os.getpid()}}
    try:
        train=import_case(w,output,'train');holdout=import_case(w,output,'holdout')
        record['data']=[{k:v for k,v in item.items() if k!='result'} for item in (train,holdout)]
        base={'model':'neo_hooke','parameters':{'mu':case['initial_mu_MPa'],'lmbda':case['lmbda_MPa']},
              'stress_unit':'MPa','time_unit':'s','time':[0.], 'deformation_gradient':[[[1.,0.,0.],[0.,1.,0.],[0.,0.,1.]]]}
        kin=driver_recipe('finite_lambda','x',lateral='free')
        base=measured_protocol(base,train['result'],kin)
        material=w.document_open(kind='material',title='유한 Neo 자유 횡수축',draft={'backend':'material.felupe','settings':base})
        material=command(w,material,'document.save')['document']
        plan_draft=from_material_document(material);plan_draft.update(budget=case['fit_budget'],seed=case['seed'])
        plan_draft['material'].update(saved_revision=material['saved_revision'],
            input_sha256=canonical_hash(material['draft']))
        for v in plan_draft['variables']:
            v['free']=v['id']=='mu'
            if v['free']:v.update(value=case['initial_mu_MPa'],lower=case['mu_bounds_MPa'][0],upper=case['mu_bounds_MPa'][1])
        for name,role,item in [('Train','fit',train),('Holdout','holdout',holdout)]:
            plan_draft['experiments'].append({'id':name,'role':role,'source':{**item['source'],
                'processing_revision':item['processing_revision'],'response':'finite_sigma'},'response':'stress_xx',
                'settings':measured_protocol(base,item['result'],kin),'kinematics':kin,'weight':1.,'scale':1.,
                'extensions':{'finite_measure':comparison_extension('x')}})
        plan=w.document_open(kind='numerical',title='유한변형 fit와 독립 holdout',draft=plan_draft)
        service=DataMaterialService(w)
        for name,role,item in [('Train','fit',train),('Holdout','holdout',holdout)]:
            proposal=service.sample_policy_preview(item['document_id'],item['processing_revision'],'finite_sigma',role=role)
            plan=service.sample_policy_adopt(plan['id'],name,proposal,session_id=plan['session_id'],
                expected_generation=plan['generation'],command_id='CfinitePolicy'+name)['document']
        assert not plan['diagnostics'],plan['diagnostics']
        arguments=w.numerical_documents.job_arguments(plan['draft'])
        assert [e['role'] for e in arguments['experiments']]==['fit','holdout']
        assert all(sum(e['mask'])==6 for e in arguments['experiments'])
        assert arguments['experiments'][0]['observations']['source_rows']==case['fit_source_rows']
        assert arguments['experiments'][1]['observations']['source_rows']==case['holdout_source_rows']
        holdout_trial_id=arguments['experiments'][1]['id']
        record.update(plan_id=plan['id'],material_id=material['id'],frozen_hash=canonical_hash(arguments['frozen_inclusion']))
        save(output/'canonical-inputs.json',arguments)
        if importlib.util.find_spec('felupe') is None:
            # Preserve actual actionable preparation error, not an algebra fallback.
            from caelab.adapters.felupe_material import FelupeMaterialAdapter
            try:FelupeMaterialAdapter().prepare(base)
            except (ImportError,ModuleNotFoundError,CapabilityUnavailable) as error:
                save(output/'native-not-run.json',{'state':'NOT_RUN','exception':type(error).__name__,'message':str(error),
                    'retry':'기존 Windows FELUPE 환경의 절대 Python 경로로 동일 명령을 실행하세요. 초안·선택·보존 관측은 유지됩니다.'})
            else:raise AssertionError('Dependency probe and actual prepare disagree')
            record['status']='PARTIAL_NATIVE_NOT_RUN'
        else:
            # Original coefficient describe/bind and actual Material evaluation.
            from caelab.adapters.felupe_material import FelupeMaterialAdapter
            adapter=FelupeMaterialAdapter();descriptors=adapter.describe_inputs(base)
            assert {d['id'] for d in descriptors}=={'mu','lmbda'}
            assert adapter.bind_inputs(base,{'mu':.8})['deformation_gradient']==base['deformation_gradient']
            material_job=command(w,material,'material.evaluate')['job'];actual=wait(w,material_job)
            actual_derived=derive(actual,'stress_xx',comparison_extension('x')['payload'])
            save(output/'actual-material.json',actual);save(output/'actual-derived.json',actual_derived)
            observed_J=[r['J'] for r in json.loads((ROOT/'examples/finite-measure/train-oracle.json').read_text())]
            actual_J=[s['J'] for s in actual_derived['extensions']['finite_measure']['payload']['actual_accepted_states']]
            assert any(abs(a-b)>1e-5 for a,b in zip(actual_J,observed_J)), 'Candidate J must differ from observations at mu=.8'
            submitted=command(w,plan,'numerical.run');fit=wait(w,submitted['job'])
            assert abs(fit['parameters']['mu']/case['mu_MPa']-1)<case['expected_mu_relative_tolerance']
            assert all(c['rmse']<case['expected_rmse_MPa'] for c in fit['curves'])
            save(output/'actual-fit.json',fit)
            successes=[c for c in fit['candidates'] if c['execution_status']=='SUCCEEDED']
            best=min(successes,key=lambda c:c['objective']);second=next((c for c in successes if c['candidate_id']!=best['candidate_id']),None)
            assert second is not None,'Need two actually evaluated candidates for retained comparison'
            evidence=[]
            for candidate in (best,second):
                cid=candidate['candidate_id'];before=len(w.manager.list())
                view=w.numerical_candidate_detail(plan['id'],submitted['job']['id'],cid)
                assert len(w.manager.list())==before
                if view['missing_experiments']:
                    # Explicit runnable action, never a consequence of row selection.
                    task=command(w,plan['id'],'numerical.detail_eval',{'source':view['source'],'candidate_id':cid})['job']
                    wait(w,task);view=w.numerical_candidate_detail(plan['id'],submitted['job']['id'],cid,attempt_job_id=task['id'])
                assert not view['missing_experiments']
                capture=command(w,plan['id'],CAPTURE,{'source':view['source'],'candidate_id':cid,
                    'attempt_job_id':view['attempt_job_id'],'purpose':SUCCESS})
                evidence.append(capture['reference'])
                for trial in view['trials']:
                    times,residual=physical_residual(trial['curve'])
                    assert any(v is not None for v in residual)
                save(output/(cid+'-detail.json'),view)
                save(output/(cid+'-physical-rows.json'),table_rows(view,holdout_trial_id))
            comparison=compare_selected_candidate_evidence(w.numerical_documents,evidence[0],evidence[1],holdout_trial_id)
            save(output/'candidate-comparison.json',comparison)
            material=w.document_read(material['id']);old=deepcopy(material)
            adopted=w.desktop.adopt(plan['id'],submitted['job']['id'],best['candidate_id'],
                material_document_id=material['id'],session_id=material['session_id'],expected_generation=material['generation'],
                command_id='CfiniteAdopt',detail_evidence=evidence[0])['document']
            try:
                w.desktop.adopt(plan['id'],submitted['job']['id'],best['candidate_id'],material_document_id=old['id'],
                    session_id=old['session_id'],expected_generation=old['generation'],command_id='CfiniteStale',detail_evidence=evidence[0])
            except ValueError:pass
            else:raise AssertionError('Stale adoption was admitted')
            material=command(w,adopted,'document.save')['document']
            record.update(status='PASS',fit_job=submitted['job']['id'],fit_hash=canonical_hash(fit),evidence=evidence)
        plan=command(w,plan['id'],'document.save')['document'];material=command(w,material['id'],'document.save')['document']
        record.update(plan_hash=canonical_hash(plan['draft']),material_hash=canonical_hash(material['draft']))
        save(output/'checkpoint.json',record)
    except Exception as error:
        record.update(status='FAILED',error=type(error).__name__+': '+str(error),traceback=traceback.format_exc())
        save(output/'failure.json',record);raise
    finally:assert w.shutdown()['joined']
    # The source CSV was uploaded as bytes; cold access must use Data retention,
    # not the fixture or current upload/job locations. Keep originals quarantined.
    quarantined=[]
    for name in ('inputs','jobs','results'):
        path=w.root/name
        assert path.is_dir(), 'Actual Workbench source path not found: '+str(path)
        files=sum(1 for p in path.rglob('*') if p.is_file())
        path.rename(output/('quarantined-'+name))
        assert not path.exists()
        quarantined.append({'original_path':str(path),'quarantine':str(output/('quarantined-'+name)),'files':files})
    save(output/'quarantine.json',quarantined)
    completed=subprocess.run([sys.executable,str(Path(__file__).resolve()),'--cold',str(output)],
        cwd=ROOT,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,timeout=150)
    (output/'cold-process.log').write_text(completed.stdout,encoding='utf-8')
    assert completed.returncode==0,completed.stdout
    save(output/'result.json',{'state':record['status'],'data_processing_plan_cold':'PASS',
        'native_fit_adoption':'PASS' if record['status']=='PASS' else 'NOT_RUN','windows_gui':'NOT_RUN'})
    print(json.dumps(json.loads((output/'result.json').read_text()),ensure_ascii=False))
    return 0 if record['status']=='PASS' else 2


if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',type=Path);parser.add_argument('--cold',type=Path)
    args=parser.parse_args()
    if args.cold:read_cold(args.cold.resolve());sys.exit(0)
    if args.output is None:parser.error('Give --output with a new output folder')
    sys.exit(run(args.output.resolve()))
