"""Existing saved Research9 -> actual Windows owner reuse; no calculation.

Prepare is file-only. Run only after the lead freezes the common owner sources.
The existing per-owner checker owns its two copied stores and child lifetimes.
"""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()
def write(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')


def sources():
    files=['tests/check_owner_open_matrix_windows.py','tests/check_owner_open_windows.py',
        'apps/research/desktop.py','apps/research/result_return.py',
        'apps/research/request_plan_window.py','apps/research/experiment_analysis_window.py',
        'apps/research/native_material_window.py','apps/research/law_native_material_window.py']
    files += ['apps/research/'+kind+'_window.py' for kind in
        ('data','material','numerical','pde','simulation','evaluation','expert','study','report')]
    return {name:sha(ROOT/name) for name in files}


def first_numeric(value,path=('settings',)):
    if type(value) in (int,float):return list(path)
    if isinstance(value,dict):
        for key,item in value.items():
            found=first_numeric(item,path+(key,))
            if found:return found
    if isinstance(value,list):
        for index,item in enumerate(value):
            found=first_numeric(item,path+(index,))
            if found:return found


def prepare(out):
    out.mkdir(parents=True,exist_ok=False)
    receipts={group:read(ROOT/'_workspace/b83-portable'/group/'cold.json') for group in
        ('report-cold-a','physics-cold-c','expert-finish-a','c1-cold-a','data-c2-finish-a','evaluation-cold-a')}
    stores={key:Path(value['second_receipt']['workspace']) for key,value in receipts.items()}
    declared=[
        ('data','data-c2-finish-a','T4129cd0a5d894a37b61ec26f8c02ed24','delimiter','DataWindow'),
        ('material','c1-cold-a','M46a5c0963d134b9a86dd01a4652c85a7','stress_unit','MaterialWindow'),
        ('numerical','c1-cold-a','N7ff9690b2efc4164a27c45fb08496ef3','budget','NumericalWindow'),
        ('pde','physics-cold-c','Q36a636b81f2c4d22bcf06088dd5a56d9',None,'PDEWindow'),
        ('simulation','physics-cold-c','Vcbdfc73248f4489b9afe3f4f99ed52cc',None,'SimulationWindow'),
        ('evaluation','evaluation-cold-a','Eccbd0505a6be44098ced1793b6b39b7e','iteration_maximum','EvaluationWindow'),
        ('expert','expert-finish-a','Xa97c1ead56d54a47902f665fd7335d10','question','ExpertWindow'),
        ('study','expert-finish-a','S48f687d480124d339c83036f4afdee0c','question','StudyWindow'),
        ('report','report-cold-a','Bd907c5c37ab742eba304f5a1c3d55a3e','title','ReportWindow')]
    cases=[]
    for kind,group,identifier,field,window in declared:
        folder=stores[group]/'workbench/documents'/identifier
        document=read(folder/'working.json');revision=document['saved_revision']
        assert document['kind']==kind and revision
        if field is None:field={'path':first_numeric(document['draft']['settings'])};assert field['path']
        case={'kind':kind,'document_id':identifier,'workspace':str(stores[group]),
            'saved_revision':revision,'dirty_field':field,'direct_cli':True,'capture':True,'clean_reopen':True,
            'expected_window_class':window,'source_revision_file':str(folder/'revisions'/revision/'revision.json'),
            'source_revision_sha256':sha(folder/'revisions'/revision/'revision.json'),
            'source_receipt':str(ROOT/'_workspace/b83-portable'/group/'cold.json')}
        if kind=='data':case['pyside']=True
        if kind in ('data','material','numerical','evaluation'):case['restore_before_accepted_close']=True
        if kind=='expert':case['reload_before_accepted_close']=True
        if kind=='report':
            previous=ROOT/'_workspace/b81-owner/matrix-01/material/flow'
            case['prepared_stores']=[str(previous/name) for name in ('한글 공백 원 보관소','다른 보관소 같은 이름')]
        write(out/(kind+'.json'),case);cases.append(case)
    inventory={str(path):sha(path) for store in stores.values() for path in store.rglob('*') if path.is_file()}
    variants=[]
    for identifier in ('N46ac034da07c4ecca95c7b97f23af768','N1b9104c9bcb449f9af38f66f2defd554'):
        d=read(stores['report-cold-a']/'workbench/documents'/identifier/'working.json')
        variants.append({'document_id':identifier,'workspace':str(stores['report-cold-a']),
            'saved_revision':d['saved_revision'],'mode':d['draft']['mode'],
            'operation':d['draft'].get('request',{}).get('operation'),
            'expected_window_class':'NumericalWindow' if d['draft']['mode']!='request' else 'ExperimentAnalysisWindow'})
    request_id='Nc54017866eba4d6b8dedbd4df4584c94'
    request=read(stores['expert-finish-a']/'workbench/documents'/request_id/'working.json')
    variants.append({'document_id':request_id,'workspace':str(stores['expert-finish-a']),
        'saved_revision':request['saved_revision'],'mode':request['draft']['mode'],
        'operation':request['draft']['request']['operation'],'expected_window_class':'RequestPlanWindow'})
    write(out/'declaration.json',{'scope':'Python Research9; Data explicitly --pyside',
        'source_selection':'B8.3 acceptance-final individual document evidence; smallest existing completed groups. Compound copied only for its retained Report.',
        'cases':cases,'additional_existing_dispatch_variants':variants,
        'native_material_variant':'No such saved backend in the selected portable copies; not manufactured',
        'source_at_prepare':sources(),'original_store_files':inventory,
        'guards_evidence':str(ROOT/'_workspace/b81-owner/process-guards-green-a'),
        'new_jobs':0,'native_solver_calls':0,'provider_calls':0,'gui_started':False,
        'observation_boundary':'Qt signals and actual product CLI; physical OS input not claimed'})
    print('PREPARED_RESEARCH9_NO_GUI',flush=True)


def run(out,selected):
    from scripts.native_check import run_native_check
    declaration=read(out/'declaration.json');results=[]
    for case in declaration['cases']:
        if selected and case['kind']!=selected:continue
        folder=out/case['kind'];folder.mkdir(exist_ok=False);launch=sources()
        write(folder/'source-at-launch.json',launch)
        result=run_native_check([sys.executable,str(ROOT/'tests/check_owner_open_windows.py'),
            str(out/(case['kind']+'.json')),str(folder/'flow')],folder/'process',240,cwd=ROOT)
        ended=sources();write(folder/'source-at-end.json',ended)
        original_unchanged=all(sha(path)==expected for path,expected in declaration['original_store_files'].items())
        changed_sources={name:{'before':expected,'after':ended[name]} for name,expected in launch.items() if ended[name]!=expected}
        record={'kind':case['kind'],'exit_code':result.exit_code,'cleanup':result.cleanup,
            'timed_out':result.timed_out,'sources_unchanged':launch==ended,
            'source_deltas':changed_sources,
            'original_stores_unchanged':original_unchanged}
        if (folder/'flow/result.json').exists():record['result']=read(folder/'flow/result.json')
        write(folder/'receipt.json',record);results.append(record)
        assert result.exit_code==0 and result.cleanup=='job_empty' and not result.timed_out,record
        assert original_unchanged,record
        # The lead explicitly permits independent Data companion and Material
        # observation corrections during other kinds. Preserve global inequality
        # and their exact deltas; never exempt the kind under examination.
        independent={'apps/research/data_window.py','apps/research/material_window.py'}
        independent.discard('apps/research/'+case['kind']+'_window.py')
        assert set(changed_sources)<=independent,record
        assert record['result']['first_owner']['window_class']==case['expected_window_class'],record
    write(out/('matrix-'+(selected or 'all')+'.json'),{'cases':results,'new_jobs':0,'native_solver_calls':0,
        'provider_calls':0,'guards_evidence':declaration['guards_evidence'],'physical_os_input_acceptance':False})


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--prepare',action='store_true');mode.add_argument('--run',action='store_true')
    parser.add_argument('--case',choices=('data','material','numerical','pde','simulation','evaluation','expert','study','report'))
    args=parser.parse_args();out=args.output.resolve()
    prepare(out) if args.prepare else run(out,args.case)
