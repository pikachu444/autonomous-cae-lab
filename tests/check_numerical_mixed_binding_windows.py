"""Bounded actual HTTP/Qt mixed-domain delivery; run only the declared DOE once."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import shutil
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT/'tests'))
from PySide6.QtCore import QThreadPool, QTimer, Qt
from PySide6.QtWidgets import QApplication, QDialogButtonBox, QInputDialog, QMessageBox, QTableWidget
from examples.s1_windows_transfer import local_service
from examples.numerical_mixed_domains import declarations
from caelab.numerical_document import request_draft
from caelab.storage import canonical_hash
from test_numerical_evaluation_workflow import wait


class Dialogs:
    def __init__(self, app):
        self.app, self.pending, self.errors = app, [], []
        self.timer = QTimer(); self.timer.setInterval(20); self.timer.timeout.connect(self.tick); self.timer.start()
    def expect(self, title, action): self.pending.append((title, action))
    def tick(self):
        dialog = self.app.activeModalWidget()
        if dialog is None or not self.pending or self.pending[0][0] != dialog.windowTitle(): return
        _, action = self.pending.pop(0)
        try: action(dialog)
        except Exception as error: self.errors.append(repr(error)); dialog.reject()


def pin():
    variables = declarations(('RK45','DOP853'))
    variables[2]['upper'] = .5
    variables[3] = {'id':'ambient','unit':'K','lower':288.,'upper':292.,'value':290.}
    candidates = [
        {'candidate_id':'C-RK45','values':{'count':1,'base_rate':.1,'ambient':290.,'solver-method':'RK45'}},
        {'candidate_id':'C-DOP853','values':{'count':2,'base_rate':.2,'ambient':292.,'solver-method':'DOP853'}},
        {'candidate_id':'C-DEPENDENT-REJECTED','values':{'count':3,'base_rate':.2,'ambient':290.,'solver-method':'RK45'}}]
    return {'variables':variables,'candidates':candidates,'count':3,'seed':17,'responses':['temperature']}


def run(folder):
    from apps.research.request_plan_window import RequestPlanWindow
    from apps.research.numerical_mixed_variables import MixedVariablesDialog
    from caelab.variable_domains import verify_retained
    folder.mkdir(parents=True, exist_ok=False)
    shutil.copytree(ROOT/'runs/numerical-mixed-binding-20261018-01/store', folder/'store')
    first = json.loads((ROOT/'runs/numerical-mixed-binding-20261018-01/first-contact.json').read_text(encoding='utf-8'))
    source_id = first['source']['document_id']
    declared = pin()
    declaration = {'backend':'pde.scipy.ode','source':first['source'],'inputs':declared,'budget':{'evaluations':3},
                   'expected':'Two actual existing SciPy ODE dispatches; one dependent upper-bound rejection with no dispatch.'}
    declaration['sha256'] = canonical_hash(declaration)
    (folder/'declaration.json').write_text(json.dumps(declaration,ensure_ascii=False,indent=2),encoding='utf-8')
    app = QApplication.instance() or QApplication([]); dialogs = Dialogs(app)
    with local_service(folder/'store') as (wb, client):
        source = client.document_open(kind='pde',document_id=source_id)
        original_source = deepcopy(source['draft'])
        window = RequestPlanWindow(client,auto_open=False,poll_interval=0);window.show()
        def settled(predicate=lambda:True):
            wait(app,lambda:not window._busy and not window._callbacks and not window._pending_adoption and predicate(),
                 lambda:window.message.text()+' '+repr(dialogs.errors))
            assert not dialogs.errors,dialogs.errors
        def accept(dialog):dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click()
        try:
            # Pick the exact saved source through the existing product command.
            draft = request_draft({'purpose':'혼합 변수 냉각 실험계획','operation':'doe',
                'inputs':{key:deepcopy(declared[key]) for key in ('count','seed','responses','candidates')},
                'budget':{'evaluations':3}})
            window.open_document(title='혼합 변수 냉각 실험계획',draft=draft);settled(lambda:window.document is not None)
            dialogs.expect('저장 모델 선택',lambda d:accept(d))
            dialogs.expect('저장 모델 선택',lambda d:d.button(QMessageBox.StandardButton.Yes).click())
            window.model_button.click();settled(lambda:window.edited_draft().get('model_source')==first['source'])
            # Existing typed descriptor picker, without fabricated parameter paths.
            def pick(dialog):
                table = dialog.findChild(QTableWidget,'declaredModelVariables')
                table.selectAll();app.processEvents();assert dialog.grab().save(str(folder/'model-variable-picker.png'));accept(dialog)
            dialogs.expect('모델 변수 선택',pick);window.variables_button.click();settled(lambda:window.variable_sheet.rowCount()==6)
            # Reuse the product's structured draft edit for the pinned declarations,
            # then exercise the actual range dialog with a cancelled and accepted edit.
            window._edit_structure(lambda value:value.__setitem__('variables',deepcopy(declared['variables'])))
            prior = deepcopy(window.edited_draft())
            def cancel_edit(dialog):
                assert isinstance(dialog,MixedVariablesDialog)
                dialog.table.item(0,4).setText('2');app.processEvents();dialog.reject()
            dialogs.expect('변수 범위',cancel_edit);window.variable_domains_button.click();settled()
            assert window.edited_draft()==prior
            def review(dialog):
                assert isinstance(dialog,MixedVariablesDialog)
                dialog.table.setCurrentCell(2,0);dialog.expression.setFocus()
                assert dialog.validate_inputs(),dialog.error.text()
                for width,height in ((1120,690),(900,650)):
                    dialog.resize(width,height);app.processEvents()
                    assert dialog.grab().save(str(folder/f'variable-domains-{width}.png'))
                dialog.accept()
            dialogs.expect('변수 범위',review);window.variable_domains_button.click();settled()
            assert window.edited_draft()['request']['inputs']['variables']==declared['variables']
            window.apply_inputs();settled(lambda:not window.local_dirty)
            assert not window.document['diagnostics'],window.document['diagnostics']
            assert window.run_button.isEnabled() and not wb.manager.list()
            # Exact pinned draft immediately before the one authorized Run.
            (folder/'submitted-draft.json').write_text(json.dumps(window.document['draft'],ensure_ascii=False,indent=2),encoding='utf-8')
            window.run_button.click();settled(lambda:bool(window.document['runs']))
            job = window.selected_job()
            wait(app,lambda:client.status(job)['state'] in {'SUCCEEDED','FAILED','REJECTED','PARTIAL_FAILURE'},lambda:str(client.status(job)))
            result = client.document_result(window.document['id'],job)
            # Preserve the result before any subsequent UI assertions.
            record = {'plan_id':window.document['id'],'job_id':job,'source':first['source'],'result':result,
                      'declaration_sha256':declaration['sha256'],'new_jobs':len(wb.manager.list())}
            (folder/'run.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
            assert [row['execution_status'] for row in result['candidates']]==['SUCCEEDED','SUCCEEDED','REJECTED']
            assert result['timing']['model_calls']==2 and result['domain_accounting']['dependency_rejections']==1
            for row in result['candidates']:verify_retained(result['domain_input'],result['variables'],row)
            for row in result['candidates'][:2]:
                assert type(row['values']['count']) is int
                assert row['values']['solver-method']==row['input_binding']['actual_inputs']['solver-method']==row['diagnostics']['solver_method']
            assert client.document_read(source_id)['draft']==original_source
            window.refresh_document();settled();window.retry_result();settled(lambda:job in window._result_cache)
            window.candidates.selectRow(1);app.processEvents()
            for width,height in ((1440,900),(960,720)):
                window.resize(width,height);app.processEvents();app.processEvents()
                assert window.grab().save(str(folder/f'doe-selected-{width}.png'))
            window.save_document();settled(lambda:not window.document['dirty'])
            record['result_reference']=client.document_result_reference(window.document['id'],job)
            record.update(saved_revision=window.document['saved_revision'],draft_sha256=canonical_hash(window.document['draft']),
                          source_unchanged=True,qt_platform=app.platformName(),
                          source_hashes={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
                           ['apps/research/request_plan_window.py','apps/research/numerical_window.py']})
            (folder/'run.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({key:record[key] for key in ('plan_id','job_id','result_reference','new_jobs','source_unchanged')},ensure_ascii=False),flush=True)
        finally:
            dialogs.timer.stop()
            for dialog in app.topLevelWidgets():
                if dialog is not window:dialog.close()
            window._allow_close=True;window.close();app.processEvents()
            assert QThreadPool.globalInstance().waitForDone(5000)


def read_retained(folder, output):
    """Continue only the named completed attempt after the pre-save ref refusal."""
    from contextlib import ExitStack
    from unittest.mock import patch
    from apps.research.request_plan_window import RequestPlanWindow
    from apps.research import desktop
    from caelab.variable_domains import verify_retained
    from examples.s1_windows_transfer import command
    output.mkdir(parents=True,exist_ok=False)
    app=QApplication.instance() or QApplication([]);dialogs=Dialogs(app);submissions=[];launches=[]
    plan_id='N54d325a90f654486b915634635b8c0c7';job='J3fb58460e7554b3a9da0fe7641541289'
    first=json.loads((ROOT/'runs/numerical-mixed-binding-20261018-01/first-contact.json').read_text(encoding='utf-8'))
    source_id=first['source']['document_id']
    def forbidden(*a,**k):submissions.append('submit');raise AssertionError('Retained workflow submitted new calculation')
    actual_launch=desktop.launch_tool
    def launched(*a,**k):
        value=actual_launch(*a,**k);launches.append(value);return value
    with local_service(folder/'store') as (wb,client),ExitStack() as stack:
        stack.enter_context(patch.object(wb,'submit',forbidden));stack.enter_context(patch.object(wb.manager,'submit',forbidden))
        stack.enter_context(patch.object(desktop,'launch_tool',launched))
        original=client.document_open(kind='pde',document_id=source_id)
        before_jobs={r['id'] for r in wb.manager.list()}
        window=RequestPlanWindow(client,document_id=plan_id,poll_interval=0);window.show()
        def settled(predicate=lambda:True):
            wait(app,lambda:not window._busy and not window._callbacks and not window._pending_adoption and predicate(),lambda:window.message.text()+repr(dialogs.errors))
            assert not dialogs.errors,dialogs.errors
        try:
            settled(lambda:window.document is not None)
            window.retry_result();settled(lambda:job in window._result_cache)
            result=deepcopy(window._result_cache[job]);result_sha=canonical_hash(result)
            (output/'raw-result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
            assert [r['execution_status'] for r in result['candidates']]==['SUCCEEDED','SUCCEEDED','REJECTED']
            assert result['timing']['model_calls']==2 and result['domain_accounting']['dependency_rejections']==1
            for row in result['candidates']:verify_retained(result['domain_input'],result['variables'],row)
            for row in result['candidates'][:2]:
                assert type(row['values']['count']) is int
                assert row['values']['solver-method']==row['input_binding']['actual_inputs']['solver-method']==row['diagnostics']['solver_method']
            window.save_document();settled(lambda:not window.document['dirty'])
            reference=client.document_result_reference(plan_id,job)
            for index in (2,1):
                window.candidates.selectRow(index);app.processEvents();app.processEvents()
                if index==2:assert not window.pde_adopt_button.isEnabled()
                for width,height in ((1440,900),(960,720)):
                    window.resize(width,height);app.processEvents();app.processEvents()
                    assert window.grab().save(str(output/f'candidate-{index}-{width}.png'))
            def cancel(dialog):
                assert dialog.grab().save(str(output/'adoption-cancel-review.png'));dialog.reject()
            dialogs.expect('후보 입력 채택 검토',cancel);window.pde_adopt_button.click();settled()
            assert client.document_read(source_id)['draft']==original['draft']
            def accept(dialog):
                assert dialog.grab().save(str(output/'adoption-accept-review.png'))
                dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok).click()
            dialogs.expect('후보 입력 채택 검토',accept);window.pde_adopt_button.click()
            settled(lambda:bool(launches))
            adopted=client.document_read(source_id)
            values=result['candidates'][1]['values'];settings=adopted['draft']['settings']
            actual_parameters={row['name']:row['value'] for row in settings['parameters']}
            assert all(actual_parameters[key]==value for key,value in values.items() if key!='solver-method')
            assert type(actual_parameters['count']) is int and settings['solver']['method']=='DOP853'
            adopted=command(client,adopted,'document.save')['document']
            raw_inputs=[]
            for row in result['candidates'][:2]:
                path=folder/'store/workbench/results'/job/row['evaluation_refs'][0]['relative']/'pde/input.json'
                payload=json.loads(path.read_text(encoding='utf-8'))
                raw_inputs.append({'path':str(path),'sha256':canonical_hash(payload),'settings':payload})
            assert len(raw_inputs)==2
            assert {r['settings']['solver']['method'] for r in raw_inputs}=={'RK45','DOP853'}
            assert canonical_hash(client.document_result(plan_id,job))==result_sha
            assert before_jobs=={r['id'] for r in wb.manager.list()} and not submissions
            record={'plan_id':plan_id,'job_id':job,'source':first['source'],'result_reference':reference,
                    'result_sha256':result_sha,'result_status':result['execution_status'],
                    'timing':result['timing'],'domain_accounting':result['domain_accounting'],
                    'adopted_document':adopted,'raw_model_inputs':raw_inputs,'launches':launches,
                    'new_jobs':0,'submissions':0,'cancel_preserves_source':True,
                    'source_hashes':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
                     ['apps/research/request_plan_window.py','apps/research/numerical_window.py']}}
            (output/'read.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({key:record[key] for key in ('plan_id','job_id','result_status','result_reference','new_jobs','submissions','launches')},ensure_ascii=False),flush=True)
        finally:
            dialogs.timer.stop();window._allow_close=True;window.close();app.processEvents()
            assert QThreadPool.globalInstance().waitForDone(5000)


def finish_retained(folder, output):
    """Read the already adopted/saved source; never repeat run or adoption."""
    from contextlib import ExitStack
    import os
    from types import SimpleNamespace
    from unittest.mock import patch
    from apps.research.request_plan_window import RequestPlanWindow
    from apps.research import desktop
    from scripts.native_check import run_native_check
    output.mkdir(parents=True,exist_ok=False)
    app=QApplication.instance() or QApplication([])
    plan_id='N54d325a90f654486b915634635b8c0c7';job='J3fb58460e7554b3a9da0fe7641541289'
    first=json.loads((ROOT/'runs/numerical-mixed-binding-20261018-01/first-contact.json').read_text(encoding='utf-8'))
    source_id=first['source']['document_id'];submissions=[]
    def forbidden(*a,**k):submissions.append('submit');raise AssertionError('Retained finish attempted calculation')
    with local_service(folder/'store') as (wb,client),ExitStack() as stack:
        stack.enter_context(patch.object(wb,'submit',forbidden));stack.enter_context(patch.object(wb.manager,'submit',forbidden))
        source=client.document_open(kind='pde',document_id=source_id)
        assert not source['dirty'] and source['draft']['settings']['solver']['method']=='DOP853'
        original_hash=canonical_hash(source['draft']);jobs={r['id'] for r in wb.manager.list()}
        window=RequestPlanWindow(client,document_id=plan_id,poll_interval=0);window.show()
        def settled(predicate=lambda:True):
            wait(app,lambda:not window._busy and not window._callbacks and predicate(),lambda:window.message.text())
        try:
            settled(lambda:window.document is not None);window.retry_result();settled(lambda:job in window._result_cache)
            result=deepcopy(window._result_cache[job]);reference=client.document_result_reference(plan_id,job)
            assert result['timing']['model_calls']==2 and result['domain_accounting']['dependency_rejections']==1
            raw_inputs=[]
            for row in result['candidates'][:2]:
                path=folder/'store/workbench/results'/job/row['evaluation_refs'][0]['relative']/'pde/input.json'
                settings=json.loads(path.read_text(encoding='utf-8'))
                assert canonical_hash(settings)==row['input_binding']['bound_settings_sha256']
                raw_inputs.append({'path':str(path),'sha256':canonical_hash(settings),'settings':settings})
            assert {r['settings']['solver']['method'] for r in raw_inputs}=={'RK45','DOP853'}
            for index in (2,1):
                window.candidates.selectRow(index);app.processEvents();app.processEvents()
                for width,height in ((1440,900),(960,720)):
                    window.resize(width,height);app.processEvents();app.processEvents()
                    assert window.grab().save(str(output/f'candidate-{index}-{width}.png'))
            hook=output/'receiver-hook';hook.mkdir()
            (hook/'sitecustomize.py').write_text('''import json, os, time
from pathlib import Path
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication
from caelab.storage import canonical_hash
original_exec=QApplication.exec
def checked_exec(app):
    started=time.monotonic()
    timer=QTimer();timer.setInterval(30)
    def inspect():
        from apps.research.pde_window import PDEWindow
        windows=[w for w in app.topLevelWidgets() if isinstance(w,PDEWindow)]
        if not windows or windows[0].document is None or windows[0]._busy or getattr(windows[0],'_callbacks',0):
            if time.monotonic()-started>25:app.exit(4)
            return
        timer.stop();window=windows[0];document=window.document
        expected=json.loads(Path(os.environ['CAELAB_TEST_EXPECTED']).read_text(encoding='utf-8'))
        assert document['id']==expected['document_id'] and canonical_hash(document['draft'])==expected['draft_sha256']
        folder=Path(os.environ['CAELAB_TEST_RECEIVER'])
        for width,height in ((1100,800),(800,700)):
            window.resize(width,height);app.processEvents();app.processEvents()
            assert window.grab().save(str(folder/('pde-return-'+str(width)+'.png')))
        (folder/'received.json').write_text(json.dumps({'document_id':document['id'],'draft_sha256':canonical_hash(document['draft']),
            'saved_revision':document['saved_revision'],'settings':document['draft']['settings'],'pid':os.getpid()},ensure_ascii=False,indent=2),encoding='utf-8')
        window._allow_close=True;window.close();app.quit()
    timer.timeout.connect(inspect);timer.start()
    return original_exec()
QApplication.exec=checked_exec
''',encoding='utf-8')
            (output/'expected.json').write_text(json.dumps({'document_id':source_id,'draft_sha256':original_hash}),encoding='utf-8')
            def owned_spawn(*args,**kwargs):
                receipt=run_native_check(args[0],output/'child-process',40,cwd=kwargs['cwd'])
                assert receipt.exit_code==0 and receipt.cleanup=='job_empty',receipt
                return SimpleNamespace(pid=receipt.pid)
            with patch.dict(os.environ,{'PYTHONPATH':os.pathsep.join((str(hook),str(ROOT),os.environ.get('PYTHONPATH',''))),
                    'CAELAB_TEST_EXPECTED':str(output/'expected.json'),'CAELAB_TEST_RECEIVER':str(output)}),patch.object(desktop.subprocess,'Popen',owned_spawn):
                launch=desktop.launch_tool(client,'pde',document_id=source_id)
            received=json.loads((output/'received.json').read_text(encoding='utf-8'))
            assert received['draft_sha256']==original_hash
            assert canonical_hash(client.document_result(plan_id,job))==reference['result_sha256']
            assert jobs=={r['id'] for r in wb.manager.list()} and not submissions
            record={'plan_id':plan_id,'job_id':job,'source':first['source'],'adopted_document':source,
                'result_reference':reference,'result_status':result['execution_status'],'timing':result['timing'],
                'domain_accounting':result['domain_accounting'],'raw_model_inputs':raw_inputs,
                'launch':launch,'received':received,'new_jobs':0,'submissions':0,
                'source_hashes':{name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in
                   ['apps/research/request_plan_window.py','apps/research/numerical_window.py']}}
            (output/'finish.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({key:record[key] for key in ('plan_id','job_id','result_reference','new_jobs','submissions','launch')},ensure_ascii=False),flush=True)
        finally:
            window._allow_close=True;window.close();app.processEvents();assert QThreadPool.globalInstance().waitForDone(5000)


if __name__=='__main__':
    if sys.argv[1]=='finish':finish_retained(Path(sys.argv[2]).resolve(),Path(sys.argv[3]).resolve())
    elif sys.argv[1]=='read':read_retained(Path(sys.argv[2]).resolve(),Path(sys.argv[3]).resolve())
    else:run(Path(sys.argv[1]).resolve())
