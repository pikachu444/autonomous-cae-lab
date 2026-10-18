"""Retain three existing Case A Post projects as exact Study sources; no solve.

Each actual ParaView invocation admits one existing registered result and saves
through Owner. Registration/cold reads use the existing native project APIs.
"""
from pathlib import Path
from copy import deepcopy
import argparse,hashlib,json,os,sys,traceback,uuid
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))
def write(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def source_hashes():
    return {name:sha(ROOT/name) for name in (
        'tests/check_case_a_post_study_windows.py','apps/desktop_post/external.py',
        'apps/desktop_post/bridge.py','apps/desktop_post/workspace.py',
        'caelab/native_project_inputs.py','caelab/native_post_dependencies.py',
        'caelab/native_project_contract.py','caelab/workbench.py')}


def source_cases(execution,observations):
    receipt=read(execution/'execution.json');observed=read(observations/'observations.json')
    rows=[]
    for case in observed['cases']:
        source=next(row for row in receipt['cases'] if row['name']==case['name']+'_CCX_J2')
        assert source['job_id']==case['CCX']['job_id'] and source['execution_status']=='SUCCEEDED'
        rows.append({'name':case['name'],'job_id':source['job_id'],'post_input':deepcopy(case['post_input'])})
    assert len(rows)==3
    return Path(receipt['store']),rows


def original_inventory(wb):
    folders=[wb.root/'jobs',wb.root/'results',wb.root/'native']
    folders.extend(wb.root/'documents'/d['id'] for d in wb.documents()['documents'] if d['kind'] in {'material','simulation'})
    folders.extend(wb.root/'inputs'/i['id'] for i in wb.inputs())
    return {str(p):sha(p) for folder in folders if folder.exists() for p in folder.rglob('*') if p.is_file()}


def check_original_inventory(baseline):
    """Separate mutable owner cursors from immutable calculation/source files."""
    mutable=[];immutable=0
    for name,before in baseline['original_files'].items():
        path=Path(name);after=sha(path) if path.is_file() else None
        if path.name=='working.json' and path.parent.parent.name=='documents':
            if after!=before:mutable.append({'path':name,'before_sha256':before,'after_sha256':after,'cause':'UNKNOWN; concurrent owner activity not yet independently attributed'})
        else:
            assert after==before,('Original immutable input/result changed',name,before,after)
            immutable+=1
    return {'immutable_files_checked':immutable,'immutable_files_unchanged':True,
        'mutable_working_deltas':mutable,'all_original_files_unchanged':not mutable}


def native_save(config_path):
    """Called on the actual ParaView GUI thread; no foreign Qt binding."""
    from paraview import simple as p,servermanager
    from apps.desktop_post import external
    from apps.desktop_post.bridge import Owner
    from apps.desktop_post.native_controls import _Windows
    from ctypes import wintypes
    config=read(config_path);out=Path(config['output']);owner=None
    result={'pid':os.getpid(),'case':config['case'],'native_solver_calls':0,'source_at_launch':source_hashes()}
    try:
        n=config['native_input']
        before={pin['path']:sha(pin['path']) for pin in n['source_pins']}
        project=external.open_result(n['path'],out/'project',input_id=n['id'],source_pins=n['source_pins'],
            native_metadata=n['native_metadata'],registration_origin=n.get('registration_origin'))
        owner=Owner();source=p.FindSource(owner.workspace.document['sources']['result']['reader_name'])
        actual_time=n['native_metadata']['time']['values'][-1]
        p.GetAnimationScene().AnimationTime=actual_time;view=p.GetActiveView();view.ViewTime=actual_time
        source.UpdatePipeline(actual_time);data=servermanager.Fetch(source)
        display=p.Show(source,view);display.Representation='Surface With Edges'
        p.ColorBy(display,('POINTS','SXX_MPa'));display.SetScalarBarVisibility(view,True)
        bar=p.GetScalarBar(p.GetColorTransferFunction('SXX_MPa'),view)
        bar.Title='Nodal S_XX [MPa]';bar.ComponentTitle='';bar.TitleFontSize=14;bar.LabelFontSize=12
        bar.Orientation='Horizontal';bar.WindowLocation='Lower Center';bar.ScalarBarLength=.7
        display.RescaleTransferFunctionToDataRange(False,True);p.ResetCamera(view)
        text=p.Text(registrationName='Retained source meaning')
        text.Text=config['case']+'\nStatic load parameter '+str(actual_time)+' / nodal extrapolation and averaging\nSynthetic comparison / engineering qualification UNKNOWN'
        label=p.Show(text,view);label.FontSize=14;label.WindowLocation='Upper Left Corner'
        p.RenderAllViews();p.SaveScreenshot(str(out/'post.png'),p.GetLayout(view),ImageResolution=[1440,900],FontScaling='Do not scale fonts')
        saved=owner.save_project()
        assert before=={pin['path']:sha(pin['path']) for pin in n['source_pins']}
        result.update(status='SAVED',project=str(saved),project_sha256=sha(saved),
            input_id=n['id'],entry_sha256=n['sha256'],source_pins_unchanged=True,
            source_pins=before,selected_load_parameter=actual_time,nodes=data.GetNumberOfPoints(),
            elements=data.GetNumberOfCells(),native_version=str(p.GetParaViewVersion()))
    except Exception as error:result.update(status='FAILED',error=str(error),traceback=traceback.format_exc())
    finally:
        if owner is not None:owner.close()
        result['source_at_end']=source_hashes()
        write(out/'native-save.json',result)
        platform=_Windows();window=platform.main_window()
        if window:
            platform.user.PostMessageW.argtypes=[wintypes.HWND,wintypes.UINT,wintypes.WPARAM,wintypes.LPARAM]
            platform.user.PostMessageW.restype=wintypes.BOOL
            platform.user.PostMessageW(window,0x10,0,0)
    return result


def save_cases(output,execution,observations,selected):
    from caelab.workbench import Workbench
    from scripts.native_check import run_native_check
    store,cases=source_cases(execution,observations)
    output.mkdir(parents=True,exist_ok=True);wb=Workbench(store,configuration={'workers':1})
    try:
        assert len(wb.manager.list())==10
        if not (output/'baseline.json').exists():write(output/'baseline.json',{'store':str(store),'jobs':wb.manager.list(),'original_files':original_inventory(wb)})
        for case in cases:
            if selected and case['name']!=selected:continue
            folder=output/case['name'];folder.mkdir(exist_ok=False)
            native=wb.native_input(case['post_input']['id'])
            assert native['sha256']==case['post_input']['sha256'] and native['kind']=='native_result'
            config={'output':str(folder),'case':case['name'],'job_id':case['job_id'],'native_input':native,
                    'registration_command_id':'C'+uuid.uuid4().hex}
            write(folder/'config.json',config)
            script=folder/'post.py'
            script.write_text('import sys\nsys.path[:0]='+repr([str(ROOT),str(ROOT/'tests')])+\
                '\nfrom check_case_a_post_study_windows import native_save\nnative_save('+repr(str(folder/'config.json'))+')\n',encoding='utf-8')
            exe=ROOT/'runs/prepost-session-20261008-01/tools/ParaView-6.2.0-Windows-Python3.12-msvc2017-AMD64/bin/paraview.exe'
            completed=run_native_check([str(exe),'--dr','--script='+str(script)],folder/'native-process',120,cwd=ROOT)
            assert completed.exit_code==0 and completed.cleanup=='job_empty' and not completed.timed_out
            saved=read(folder/'native-save.json');assert saved['status']=='SAVED',saved
        baseline=read(output/'baseline.json')
        assert all(sha(p)==h for p,h in baseline['original_files'].items())
        assert wb.manager.list()==baseline['jobs']
    finally:wb.shutdown(timeout=10)


def register_cases(output,execution,observations,selected):
    from caelab.workbench import Workbench
    from caelab.native_project_inputs import context_from_workbench,register_saved,verify_registered
    from caelab.native_project_contract import REFERENCE_KEYS
    store,cases=source_cases(execution,observations);roots={};saved_cases=[]
    for case in cases:
        if selected and case['name']!=selected:continue
        saved=read(output/case['name']/'native-save.json');project=Path(saved['project'])
        root_id='CaseAPost_'+case['name'];roots[root_id]=str(project.parent)
        saved_cases.append((case,saved,project,root_id))
    write(output/'approved-roots.json',{'store':str(store),'input_roots':roots,'scope':'exact actual saved closure folders only'})
    wb=Workbench(store,configuration={'workers':1,'input_roots':roots});records=[];references={};launch=source_hashes()
    try:
        assert len(wb.manager.list())==10
        context=context_from_workbench(wb)
        for case,saved,project,root_id in saved_cases:
            config=read(output/case['name']/'config.json')
            admitted=register_saved(context,{'mode':'selected_file','native_kind':'post','root_id':root_id,
                'relative':project.relative_to(Path(roots[root_id])).as_posix()},command_id=config['registration_command_id'])
            reference=admitted['reference'];assert set(reference)==REFERENCE_KEYS
            verified=verify_registered(context,reference,full=True);assert verified.reference==reference
            available=wb.research_reference(reference);assert available['status']=='AVAILABLE',available
            references[case['name']]=reference;records.append({'case':case['name'],'registration':admitted,'research_reference':available,'project':str(project),'project_sha256':sha(project)})
        baseline=read(output/'baseline.json');assert wb.manager.list()==baseline['jobs']
        inventory=check_original_inventory(baseline);write(output/'mutable-working-delta.json',inventory['mutable_working_deltas'])
        assert all(sha(row['project'])==row['project_sha256'] for row in records)
        write(output/'registration.json',{'status':'REGISTERED','workspace':str(store),'cases':records,'jobs_before':10,'jobs_after':10,'new_jobs':0,'solver_calls':0,
            'source_at_launch':launch,'source_at_end':source_hashes(),'original_inventory':inventory,'saved_post_projects_unchanged':True})
        if len(references)==3:write(output/'post-references.json',references)
        else:write(output/'partial-references.json',references)
    except Exception as error:
        failure=output/'registration-failed.json'
        if failure.exists():failure=output/('registration-failed-'+uuid.uuid4().hex[:8]+'.json')
        write(failure,{'status':'FAILED','error':str(error),'traceback':traceback.format_exc(),'cases':records,'workspace':str(store),'solver_calls':0,
            'source_at_launch':launch,'source_at_end':source_hashes()})
        raise
    finally:wb.shutdown(timeout=10)


def cold(output):
    from caelab.workbench import Workbench
    from caelab.native_project_inputs import context_from_workbench,verify_registered
    declaration=read(output/'approved-roots.json');refs=read(output/'post-references.json')
    wb=Workbench(declaration['store'],configuration={'workers':1,'input_roots':declaration['input_roots']});launch=source_hashes()
    try:
        def denied(*args,**kwargs):raise AssertionError('Cold exact-source read may not submit work.')
        wb.submit=denied;wb.manager.submit=denied
        rows={}
        for name,reference in refs.items():
            assert verify_registered(context_from_workbench(wb),reference,full=True).reference==reference
            rows[name]=wb.research_reference(reference);assert rows[name]['status']=='AVAILABLE',rows[name]
        baseline=read(output/'baseline.json');assert wb.manager.list()==baseline['jobs']
        inventory=check_original_inventory(baseline)
        registration=read(output/'registration.json')
        assert all(sha(row['project'])==row['project_sha256'] for row in registration['cases'])
        write(output/'cold.json',{'status':'AVAILABLE','pid':os.getpid(),'cases':rows,'workspace':declaration['store'],
            'jobs_before':10,'jobs_after':10,'new_jobs':0,'solver_calls':0,'original_inventory':inventory,
            'saved_post_projects_unchanged':True,'source_at_launch':launch,'source_at_end':source_hashes()})
    finally:wb.shutdown(timeout=10)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True);parser.add_argument('--execution',type=Path)
    parser.add_argument('--observations',type=Path);parser.add_argument('--case')
    mode=parser.add_mutually_exclusive_group(required=True);mode.add_argument('--save',action='store_true');mode.add_argument('--register',action='store_true');mode.add_argument('--cold',action='store_true')
    args=parser.parse_args();out=args.output.resolve()
    if args.cold:cold(out)
    else:
        if not args.execution or not args.observations:parser.error('--execution and --observations are required')
        (save_cases if args.save else register_cases)(out,args.execution.resolve(),args.observations.resolve(),args.case)
