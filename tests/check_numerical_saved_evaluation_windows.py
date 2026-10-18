"""Observe the unchanged desktop launch and exact stage link in its real process.

The private startup observer drives Qt signals, not OS pointer/keyboard input.
It changes no product source and cannot submit a calculation to the owned server.
"""
from contextlib import ExitStack
from copy import deepcopy
import hashlib
import json
import os
from pathlib import Path
import sys
import time
from unittest.mock import patch


def observe_reference_process():
    """Attach once to the actual ReferenceWindow created by its original main."""
    folder=Path(os.environ['CAELAB_READONLY_CAPTURE'])
    expected=json.loads((folder/'expected.json').read_text(encoding='utf-8'))
    def profile(frame,event,arg):
        if (event!='return' or frame.f_code.co_name!='__init__' or
                not frame.f_code.co_filename.replace('\\','/').endswith('/apps/research/reference_window.py')):
            return
        window=frame.f_locals.get('self')
        if not window or getattr(window,'reference',{}).get('document_kind')!='evaluation':return
        sys.setprofile(None)
        from PySide6.QtCore import QTimer,QUrl
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance();state={'phase':0};deadline=time.monotonic()+55
        timer=QTimer(window);timer.setInterval(30)
        def step():
            try:
                if time.monotonic()>deadline:raise TimeoutError('Actual reference windows did not settle')
                phase=state['phase']
                if phase==0:
                    if window._busy or window.value is None:return
                    assert window.value['status']=='AVAILABLE',window.value
                    assert window.reference==expected['evaluation_reference']
                    body=window.content.body.toPlainText()
                    for text in ('계산 단계','입력 연결','결과','PDE 저장 입력 열기',expected['stage_name'],'1/s','K'):
                        assert text in body,(text,body)
                    assert expected['stage_reference']['document_id'] not in body
                    assert expected['stage_reference']['input_sha256'] not in body
                    state['evaluation_body']=body
                    window.resize(1100,780);state['phase']=1
                elif phase==1:
                    assert window.grab().save(str(folder/'saved-evaluation-1100.png'))
                    window.resize(800,700);state['phase']=2
                elif phase==2:
                    assert window.grab().save(str(folder/'saved-evaluation-800.png'))
                    window.content.body.anchorClicked.emit(QUrl('saved-stage:0'))
                    state['phase']=3
                elif phase==3:
                    if not window._candidate_windows:return
                    child=window._candidate_windows[0]
                    if child._busy or child.value is None:return
                    assert child.reference==expected['stage_reference']
                    assert child.value['document']['draft']==expected['stage_draft']
                    body=child.content.body.toPlainText()
                    for text in ('0.75','1/s','K','-rate*(temperature-ambient)'):
                        assert text in body,(text,body)
                    state['stage_body']=body;state['child_reference']=child.reference
                    child.resize(1100,780);state['phase']=4
                elif phase==4:
                    child=window._candidate_windows[0]
                    assert child.grab().save(str(folder/'saved-pde-stage-1100.png'))
                    child.resize(800,700);state['phase']=5
                else:
                    child=window._candidate_windows[0]
                    assert child.grab().save(str(folder/'saved-pde-stage-800.png'))
                    state.update(status='PASS',pid=os.getpid(),parent_pid=os.getppid(),qt_platform=app.platformName(),
                        exact_evaluation_reference=window.reference,exact_stage_reference=child.reference)
                    (folder/'child.json').write_text(json.dumps(state,ensure_ascii=False,indent=2),encoding='utf-8')
                    timer.stop();child.close();window.close();app.quit()
            except BaseException as error:
                timer.stop()
                (folder/'child-error.json').write_text(json.dumps({'error':repr(error),'phase':state['phase']},indent=2),encoding='utf-8')
                for child in window._candidate_windows:child.close()
                window.close();app.exit(1)
        timer.timeout.connect(step);timer.start()
    sys.setprofile(profile)


def main(store,folder,finish_record):
    from scipy.interpolate import RBFInterpolator
    from apps.research import desktop
    from examples.s1_windows_transfer import local_service
    from caelab.storage import canonical_hash
    from caelab.evaluation_definition import document_reference
    folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=False)
    saved=json.loads(Path(finish_record).read_text(encoding='utf-8'))
    paths=('apps/research/reference_content.py','apps/research/reference_window.py','apps/research/desktop.py')
    hashes=lambda:{p:hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths}
    before_sources=hashes();calls=[];references=[];processes=[]
    def forbidden(*args,**kwargs):calls.append('solve/fit/predict/submit');raise AssertionError('Read-only acceptance attempted calculation')
    with local_service(Path(store).resolve()) as (wb,client),ExitStack() as stack:
        jobs_before={row['id'] for row in wb.manager.list()}
        stack.enter_context(patch.object(wb.manager,'submit',forbidden))
        stack.enter_context(patch.object(RBFInterpolator,'__init__',forbidden))
        stack.enter_context(patch.object(RBFInterpolator,'__call__',forbidden))
        current=client.document_read(saved['old_source']['document_id'])
        assert document_reference(current)==saved['adopted_source']
        original={**saved['old_source'],'kind':'document','document_kind':'evaluation'}
        old=client.research_reference(original)['document']
        source=old['draft']['stages'][0]['source']
        stage_reference={**source,'kind':'document','document_kind':source['kind']}
        stage=client.research_reference(stage_reference)['document']
        assert stage['draft']['settings']['parameters'][0]['value']==.75
        current_stage=client.document_read(saved['new_stage_source']['document_id'])
        assert current_stage['draft']['settings']['parameters'][0]['value']==saved['selected_values']['cooling_rate']
        owner_before={doc['id']:canonical_hash(doc) for doc in (current,current_stage,client.document_read(source['document_id']))}
        plan_ref=saved['plan_result_reference']
        old_result=canonical_hash(client.document_result(plan_ref['document_id'],plan_ref['job_id']))
        assert old_result==plan_ref['result_sha256']
        expected={'evaluation_reference':original,'stage_reference':stage_reference,'stage_draft':stage['draft'],
            'stage_name':old['draft']['stages'][0]['name']}
        (folder/'expected.json').write_text(json.dumps(expected,ensure_ascii=False,indent=2),encoding='utf-8')
        # Startup observation preserves the original executable/module/arguments.
        # The observer attaches only after the real product window constructor.
        bootstrap=folder/'startup';bootstrap.mkdir()
        (bootstrap/'sitecustomize.py').write_text(
            "import os,runpy\nrunpy.run_path(os.environ['CAELAB_READONLY_OBSERVER'],run_name='_caelab_readonly_observer')\n",encoding='utf-8')
        stack.enter_context(patch.dict(os.environ,{
            'PYTHONPATH':str(bootstrap)+os.pathsep+os.environ.get('PYTHONPATH',''),
            'CAELAB_READONLY_OBSERVER':str(Path(__file__).resolve()),'CAELAB_READONLY_CAPTURE':str(folder)}))
        real_reader=wb.research_reference
        def read(reference):references.append(deepcopy(reference));return real_reader(reference)
        stack.enter_context(patch.object(wb,'research_reference',read))
        original_popen=desktop.subprocess.Popen
        def tracked_popen(*args,**kwargs):
            process=original_popen(*args,**kwargs);processes.append(process);return process
        stack.enter_context(patch.object(desktop.subprocess,'Popen',tracked_popen))
        try:
            receipt=desktop.open_saved_reference(client,saved['old_source'])
            (folder/'launch.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
            assert len(processes)==1 and receipt['pid']==processes[0].pid
            assert processes[0].wait(timeout=65)==0,(folder/'child-error.json').read_text(encoding='utf-8') if (folder/'child-error.json').exists() else 'Reference process failed'
            child=json.loads((folder/'child.json').read_text(encoding='utf-8'))
            assert child['status']=='PASS'
            assert receipt['pid'] in (child['pid'],child['parent_pid']),(receipt,child)
            assert references==[original,original,stage_reference],references
            for identifier,expected_hash in owner_before.items():
                assert canonical_hash(client.document_read(identifier))==expected_hash
            assert canonical_hash(client.document_result(plan_ref['document_id'],plan_ref['job_id']))==old_result
            assert {row['id'] for row in wb.manager.list()}==jobs_before and not calls
            assert hashes()==before_sources,'Common source changed while the acceptance was running'
            result={'launch':receipt,'old_source':saved['old_source'],'adopted_source':saved['adopted_source'],
                'stage_reference':stage_reference,'stage_rate':.75,'current_adopted_rate':saved['selected_values']['cooling_rate'],
                'exact_reference_reads':references,'read_count':len(references),'owner_hashes_unchanged':owner_before,
                'result_sha256':old_result,'new_jobs':0,'solver_fit_predict_submissions':0,
                'qt_platform':child['qt_platform'],'source_hashes':before_sources,
                'driver_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
            (folder/'readonly.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps(result,ensure_ascii=False),flush=True)
        finally:
            for process in processes:
                if process.poll() is None:process.terminate()
                process.wait(timeout=5)


if __name__=='_caelab_readonly_observer':observe_reference_process()
elif __name__=='__main__':
    sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
    main(*sys.argv[1:])
