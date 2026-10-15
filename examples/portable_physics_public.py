"""Public PDE/Simulation copy/edit/explicit-run/two-process resume, no AI/CAD.

Uses the existing small scikit-fem PDE and thermal adapters. Four evaluations:
one original and one explicit destination evaluation per owner. Cold reads,
Undo/save/recopy never evaluate. Only new output children are created/moved.
"""
from contextlib import contextmanager,ExitStack
from copy import deepcopy
import argparse,json,os,subprocess,sys,time
from pathlib import Path
from unittest.mock import patch
from caelab.workbench import Workbench
from caelab.storage import canonical_hash,save_json,load_json
from caelab.evaluation import file_hash
from caelab.portable_project import inspect_copy,create_copy,open_project,verify_project
from caelab.portable_project_physics import read_execution
from caelab.jobs import TERMINAL


def command(wb,doc,operation,arguments=None):
    return wb.document_command(doc['id'],operation,arguments or {},session_id=wb.session_id,
                               expected_generation=doc['generation'])


def save(wb,doc):return command(wb,doc,'document.save')['document']


def wait(wb,job_id):
    deadline=time.monotonic()+90
    while time.monotonic()<deadline:
        job=wb.manager.status(job_id)
        if job['state'] in TERMINAL:return job
        time.sleep(.01)
    raise TimeoutError('Owned small evaluation did not terminate')


def evaluate(wb,doc):
    receipt=command(wb,doc,doc['kind']+'.evaluate');job=wait(wb,receipt['job']['id'])
    if job['state']!='SUCCEEDED':raise AssertionError(job)
    value=wb.document_result(doc['id'],job['id'])
    if value['execution_status']!='SUCCEEDED':raise AssertionError(value)
    return save(wb,wb.document_read(doc['id'])),value,job['id']


def hashes(wb,doc,job):
    run=next(r for r in doc['runs'] if r['job_id']==job)
    root=wb._document_owner(doc['id'])._folder(doc['id'])/'revisions'/run['retained_result']['revision']/'results'/job
    return {p.relative_to(root).as_posix():file_hash(p) for p in root.rglob('*') if p.is_file()}


@contextmanager
def no_execution(wb):
    def forbidden(*a,**k):raise AssertionError('Read/edit/Undo/save/recopy attempted execution or live-job access')
    with ExitStack() as stack:
        for obj,name in ((wb,'submit'),(wb.manager,'submit'),(wb.manager,'status'),(wb.manager,'result')):
            stack.enter_context(patch.object(obj,name,forbidden))
        stack.enter_context(patch('caelab.evaluation.run',forbidden))
        yield


def publish(wb,documents,destination):
    plan=inspect_copy(wb,[d['id'] for d in documents])
    assert plan['status']=='READY',plan['issues']
    receipt=create_copy(wb,plan,destination,approved=True,command_id='Cphysics'+os.urandom(8).hex(),session_id=wb.session_id)
    assert receipt['executed'] is False
    return receipt


def fixture(folder):
    from caelab.pde_document import default_draft
    from caelab.simulation_document import default_draft as simulation
    wb=Workbench(folder)
    try:
        docs=[];evidence={}
        for kind,draft in [('pde',default_draft('pde.scikit_fem.dimensioned')),
                           ('simulation',simulation('thermal.scikit_fem.rectangle'))]:
            doc=wb.document_open(kind=kind,title='공개 '+('온도 약형식' if kind=='pde' else '정상 열전도'),draft=draft)
            doc,value,job=evaluate(wb,doc)
            docs.append(doc)
            evidence[kind]={'document_id':doc['id'],'draft':deepcopy(doc['draft']),
                'original_run':deepcopy(doc['runs'][-1]),'job_id':job,'result_sha256':canonical_hash(value),
                'files':hashes(wb,doc,job),'response_names':list(value['responses'])}
        return wb,docs,evidence
    except BaseException:wb.shutdown();raise


def changed(doc):
    draft=deepcopy(doc['draft'])
    if doc['kind']=='pde':draft['settings']['parameters'][0]['value']*=1.1
    else:draft['settings']['boundary_temperature']['value']+=2.
    return draft


def cold(output,phase):
    output=Path(output);evidence=load_json(output/'evidence.json')
    receipt=load_json(output/('first.json' if phase==1 else 'second.json'))
    wb=open_project(output/('사본 1' if phase==1 else '재복사 2'))
    try:
        docs=[]
        with no_execution(wb):
            for row in receipt['documents']:
                doc=wb.document_read(row['document_id']);origin=evidence[doc['kind']]
                result=wb.document_result(doc['id'],origin['job_id'])
                assert canonical_hash(result)==origin['result_sha256']
                assert hashes(wb,doc,origin['job_id'])==origin['files']
                view=read_execution(wb._document_owner(doc['id']),doc['id'],origin['job_id'])
                assert view['source_document_id']==origin['document_id']
                assert view['original_run']['arguments']==origin['original_run']['arguments']
                assert view['original_run']['input_sha256']==origin['original_run']['input_sha256']
                assert doc['runs'][0]['retained_state']==origin['original_run']['retained_state']
                edit=changed(doc);before=deepcopy(doc['draft'])
                updated=command(wb,doc,doc['kind']+'.update',{'draft':edit})['document']
                undone=command(wb,updated,'document.undo')['document'];assert undone['draft']==before
                redone=command(wb,undone,'document.redo')['document'];assert redone['draft']==edit
                docs.append(save(wb,redone))
            assert not wb.manager.list()
        if phase==1:
            current={}
            for i,doc in enumerate(docs):
                assert not next(r for r in doc['runs'] if r['job_id']==evidence[doc['kind']]['job_id'])['is_current_input']
                doc,result,job=evaluate(wb,doc);docs[i]=doc
                assert job!=evidence[doc['kind']]['job_id']
                current[doc['kind']]={'job_id':job,'result_sha256':canonical_hash(result),'files':hashes(wb,doc,job)}
                assert canonical_hash(wb.document_result(doc['id'],evidence[doc['kind']]['job_id']))==evidence[doc['kind']]['result_sha256']
            save_json(output/'current.json',current)
            with no_execution(wb):save_json(output/'second.json',publish(wb,docs,output/'재복사 2'))
        else:
            current=load_json(output/'current.json')
            with no_execution(wb):
                for doc in docs:
                    row=current[doc['kind']]
                    assert canonical_hash(wb.document_result(doc['id'],row['job_id']))==row['result_sha256']
                    assert hashes(wb,doc,row['job_id'])==row['files']
            assert not wb.manager.list()
        assert verify_project(wb.workspace)['status']=='READY'
        save_json(output/f'cold-{phase}.json',{'status':'PASS','pid':os.getpid(),'phase':phase,
            'reads_execute':False,'new_explicit_evaluations':2 if phase==1 else 0,'solver_native_campaign':False})
    finally:
        closed=wb.shutdown();assert closed['joined'] and not closed['pending']


def main():
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True,type=Path)
    parser.add_argument('--cold',type=int,choices=(1,2));args=parser.parse_args();output=args.output.resolve()
    if args.cold:cold(output,args.cold);return
    output.mkdir(parents=True,exist_ok=False)
    wb,docs,evidence=fixture(output/'원 store')
    try:
        save_json(output/'evidence.json',evidence)
        save_json(output/'first.json',publish(wb,docs,output/'사본 1'))
    finally:
        closed=wb.shutdown();assert closed['joined'] and not closed['pending']
    (output/'원 store').rename(output/'원 store.preserved')
    pids=[]
    for phase in (1,2):
        if phase==2:(output/'사본 1').rename(output/'사본 1.preserved')
        completed=subprocess.run([sys.executable,'-m','examples.portable_physics_public','--output',str(output),'--cold',str(phase)],
            capture_output=True,text=True,encoding='utf-8',timeout=150)
        (output/f'process-{phase}.log').write_text(completed.stdout+completed.stderr,encoding='utf-8')
        if completed.returncode:raise RuntimeError(completed.stdout+completed.stderr)
        pids.append(load_json(output/f'cold-{phase}.json')['pid'])
    assert len(set([os.getpid(),*pids]))==3
    record={'status':'PASS','parent_pid':os.getpid(),'cold_pids':pids,'original_stores_preserved':True,
        'original_evaluations':2,'new_explicit_evaluations':2,'read_edit_save_recopy_evaluations':0,
        'provider_calls':0,'engineering_release':'NOT_RELEASED','GUI':'NOT_RUN'}
    save_json(output/'result.json',record);print(json.dumps(record,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
