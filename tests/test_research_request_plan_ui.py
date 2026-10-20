"""Actual Qt request editor and actual Numerical owner/evaluator checks.

No provider is used: request Plans execute the existing FELUPE calculation only
when Run is clicked. A separate transport latency double checks callback races.
"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
from copy import deepcopy
import threading
import time

import pytest
pytest.importorskip('PySide6')
pytest.importorskip('felupe')
from PySide6.QtWidgets import QApplication, QInputDialog
from apps.research.request_plan_window import RequestPlanWindow, DATA
from caelab.workbench import Workbench
from caelab.numerical_document import request_draft
from caelab.material_document import default_draft as material_draft


@pytest.fixture
def app():
    return QApplication.instance() or QApplication([])


@pytest.fixture
def workbench(tmp_path):
    workbench = Workbench(tmp_path)
    yield workbench
    assert workbench.shutdown()['joined']


class InProcessClient:
    """Transport double; all document/evaluation effects use the real Workbench."""
    def __init__(self, workbench):
        self.workbench = workbench
        self.release = None
    def document_open(self, **arguments):
        return self.workbench.document_open(**arguments)
    def document_read(self, identifier):
        if self.release is not None:
            assert self.release.wait(5)
        return self.workbench.document_read(identifier)
    def document_command(self, *arguments, **kwargs):
        return self.workbench.document_command(*arguments, **kwargs)
    def document_result(self, *arguments, **kwargs):
        return self.workbench.document_result(*arguments, **kwargs)
    def document_result_reference(self, *arguments):
        return self.workbench.document_result_reference(*arguments)
    def document_result_metadata(self, *arguments):
        return self.workbench.document_result_metadata(*arguments)
    def result_followup(self, *arguments, **kwargs):
        return self.workbench.desktop.result_followup(*arguments, **kwargs)
    def status(self, identifier):
        return self.workbench.manager.status(identifier)
    def documents(self):
        return self.workbench.documents()


def wait(app, predicate):
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(.005)
    messages = [widget.message.text() for widget in app.topLevelWidgets() if isinstance(widget, RequestPlanWindow)]
    raise AssertionError('request Plan Qt callback did not settle: ' + repr(messages))


def valid_request():
    return request_draft({'purpose': 'Evaluate the actual material point', 'operation': 'evaluate',
        'inputs': material_draft(), 'budget': {'evaluations': 1}})


@pytest.mark.parametrize('same_model', [False, True])
def test_plan_reopens_bound_native_model_or_its_relinked_save(app, workbench, monkeypatch, same_model):
    client = InProcessClient(workbench)
    draft = valid_request()
    draft['source'] = {'discussion_id': 'Xsource', 'job_id': 'Jsource'}
    model = {'original_path': 'C:/models/original.FCStd', 'saved_path': 'C:/models/saved.FCStd'}
    latest = {'original_path': model['original_path'] if same_model else 'C:/models/other.FCStd',
              'saved_path': 'C:/models/relocated.FCStd'}
    read = client.document_read
    client.document_read = lambda identifier: ({'id': 'Xsource',
        'draft': {'context': {'workbench': {'model': latest}}}, 'runs': [{'job_id': 'Jsource',
        'draft': {'context': {'workbench': {'model': model}}}}]} if identifier == 'Xsource' else read(identifier))
    opened = []
    monkeypatch.setattr('apps.research.desktop.launch_pre',
        lambda client, **kwargs: opened.append(kwargs) or {'status': 'LAUNCH_REQUESTED'})
    window = RequestPlanWindow(client, auto_open=False, poll_interval=0)
    try:
        window.open_document(draft=draft)
        wait(app, lambda: window.document is not None and not window._busy)
        window.model_open_button.click()
        wait(app, lambda: not window._busy and bool(opened))
        assert opened[0]['source'] == (latest['saved_path'] if same_model else model['saved_path'])
        assert opened[0]['discussion_id'] == 'Xsource'
        assert workbench.manager.list() == []
    finally:
        window._allow_close = True
        window.close()


@pytest.mark.parametrize('backend',['structure.calculix.frozen','structure.calculix.contact','structure.calculix.pretension'])
def test_native_model_refresh_edits_the_plan_without_submitting(app, workbench, monkeypatch, backend):
    client = InProcessClient(workbench)
    calls = []
    def refresh(plan_id, **arguments):
        calls.append((plan_id, arguments))
        return {'status': 'READY', 'executed': False, 'backend': backend,
                'settings': {'data_id': 'Dupdated'}}
    client.native_plan_input = refresh
    draft = request_draft({'purpose': '사용자 모델의 접촉 조건 수정', 'operation': 'evaluate',
        'inputs': {'backend': backend, 'settings': {'data_id': 'Doriginal'}},
        'budget': {'evaluations': 1}}, source={'discussion_id': 'Xsource', 'turn_id': 'Aturn',
        'proposal_index': 0, 'proposal_sha256': 'a' * 64, 'job_id': 'Jsource',
        'input_revision': 'Isource', 'input_sha256': 'b' * 64})
    window = RequestPlanWindow(client, auto_open=False, poll_interval=0)
    try:
        window.open_document(draft=draft)
        wait(app, lambda: window.document is not None and not window._busy)
        assert window.native_update_button.isEnabled()
        # Adding a different result to the conversation cannot redirect this
        # Plan away from the model selected when its source reply was requested.
        original_read = client.document_read
        client.document_read = lambda identifier: ({'draft': {'context': {
            'engineering_context': {'job_id': 'JlaterModel'}}}, 'runs': [
            {'job_id': 'Jsource', 'draft': {'context': {'engineering_context': {'job_id': 'JoriginalModel'}}}}]}
            if identifier == 'Xsource' else original_read(identifier))
        opened_models = []
        monkeypatch.setattr('apps.research.desktop.open_origin',lambda selected,job:opened_models.append(job))
        window.model_open_button.click()
        wait(app,lambda:not window._busy and bool(opened_models))
        assert opened_models == ['JoriginalModel']
        window.native_update_button.click()
        wait(app, lambda: not window._busy and window.local_dirty)
        assert window.edited_draft()['request']['inputs']['settings'] == {'data_id': 'Dupdated'}
        assert workbench.document_read(window.document['id'])['draft'] == draft
        assert window.edited_draft()['source'] == draft['source']
        assert len(calls) == 1 and workbench.manager.list() == []
        if os.environ.get('CAELAB_GUI_CAPTURE_DIR'):
            from pathlib import Path
            captures = Path(os.environ['CAELAB_GUI_CAPTURE_DIR'])
            captures.mkdir(parents=True, exist_ok=True)
            window.show()
            for width, height in ((1440, 900), (1100, 760)):
                window.resize(width, height)
                for _ in range(10):
                    app.processEvents()
                    time.sleep(.02)
                assert window.screen().grabWindow(int(window.winId())).save(str(captures / ('native-plan-' + str(width) + '.png')))
    finally:
        window._allow_close = True
        window.close()


def find_input(window, path):
    def visit(item):
        if tuple(item.data(0, DATA)['path']) == path:
            return item
        for index in range(item.childCount()):
            found = visit(item.child(index))
            if found:
                return found
    return visit(window.inputs.topLevelItem(0))


def opened(app, workbench):
    window = RequestPlanWindow(InProcessClient(workbench), auto_open=False, poll_interval=0)
    window.open_document(draft=valid_request())
    wait(app, lambda: window.document is not None and not window._busy)
    return window


def test_budget_check_matches_submission_without_changing_or_running_saved_draft(app, workbench):
    from caelab.numerical_document import request_diagnostics
    draft = valid_request()
    draft['request']['operation'] = 'optimize'
    draft['request']['inputs'].update(
        variables=[{'id': 'E', 'unit': 'MPa', 'value': 1000., 'lower': 500., 'upper': 2000., 'transform': 'linear'}],
        objective={'response': 'stress_xx', 'unit': 'MPa', 'component': 'xx', 'location': 'material_point',
                   'reduction': 'max', 'direction': 'minimize'},
        options={'population_size': 5, 'max_generations': 1})
    draft['request']['budget']['evaluations'] = 2
    original = deepcopy(draft)
    issues = request_diagnostics(draft)
    assert issues and issues[0]['blocks_evaluation']
    assert 'population exceeds' in issues[0]['message']
    assert draft == original
    with pytest.raises(ValueError, match='population exceeds'):
        workbench._request_plan_arguments(draft['request'])
    window = RequestPlanWindow(InProcessClient(workbench), auto_open=False, poll_interval=0)
    try:
        window.open_document(draft=draft)
        wait(app, lambda: window.document is not None and not window._busy)
        assert window.document['diagnostics'] and not window.run_button.isEnabled()
        window.save_document()
        wait(app, lambda: not window._busy and window.document['saved_revision'] is not None)
        assert window.document['draft'] == original and not workbench.manager.list()
        window.evaluations.setText('10')
        window.apply_inputs()
        wait(app, lambda: not window._busy and not window.local_dirty)
        assert not window.document['diagnostics'] and window.run_button.isEnabled()
        assert window.document['draft']['request']['inputs'] == original['request']['inputs']
        assert not workbench.manager.list()
    finally:
        window._allow_close = True
        window.close()


@pytest.fixture
def edit_windows(app, monkeypatch):
    """Close only this test's editors; editing must not start native/provider work."""
    import subprocess
    from PySide6.QtCore import QThreadPool
    from caelab.adapters.felupe_material import FelupeMaterialAdapter
    previous = set(app.topLevelWidgets())
    def forbidden(*args, **kwargs):
        pytest.fail('This focused editor check must not execute FELUPE, native processes or a provider')
    monkeypatch.setattr(FelupeMaterialAdapter, 'prepare', forbidden)
    monkeypatch.setattr(subprocess, 'run', forbidden)
    class ForbiddenProcess(subprocess.Popen):
        def __init__(self, *args, **kwargs):
            forbidden(*args, **kwargs)
    monkeypatch.setattr(subprocess, 'Popen', ForbiddenProcess)
    monkeypatch.setattr(Workbench, 'assistance_call', forbidden)
    yield
    windows = [window for window in app.topLevelWidgets() if window not in previous
               and isinstance(window, RequestPlanWindow)]
    for window in windows:
        release = getattr(window.client, 'release', None)
        if release is not None:
            release.set()
    wait(app, lambda: all(not window._busy for window in windows))
    for window in windows:
        window._allow_close = True
        window.close()
        window.deleteLater()
    app.processEvents()
    assert QThreadPool.globalInstance().waitForDone(2000)


@pytest.fixture
def retained_studies(app, workbench, monkeypatch):
    """Actual owner, JobManager and numerical engine; cheap algebraic evaluator."""
    from caelab.backends import Backend, _registry
    def model(values, settings):
        x = values['x']
        if x > .9:
            return {'execution_status':'FAILED','responses':{},'diagnostics':{'failure_reason':'Declared synthetic domain limit'}}
        return {'execution_status':'SUCCEEDED','responses':{'cost':{
            'kind':'scalar','value':x*x,'unit':'MPa','component':'scalar','location':'model','reduction':'none'}}}
    monkeypatch.setitem(_registry, 'test.request.numeric', Backend('test.request.numeric', ('prepared',), lambda:model))
    variables = [{'id':'x','unit':'1','value':.5,'lower':0.,'upper':1.,'transform':'linear'}]
    records = []
    for name, points in [('Training',[0.,.2,.4,.6,.8,.95]), ('Holdout',[.1,.3,.5,.7])]:
        draft = request_draft({'purpose':name,'operation':'doe','inputs':{
            'backend':'test.request.numeric','variables':variables,'count':len(points),'candidates':[{'values':{'x':x}} for x in points]},
            'budget':{'evaluations':len(points)}})
        document = workbench.document_open(kind='numerical',title=name,draft=draft)
        receipt = workbench.document_command(document['id'],'numerical.run',{},
            session_id=document['session_id'],expected_generation=document['generation'])
        job = receipt['job']['id']
        try:
            wait(app, lambda:workbench.manager.status(job)['state'] in {'SUCCEEDED','PARTIAL_FAILURE','FAILED','REJECTED','CANCELLED'})
        except AssertionError:
            raise AssertionError(workbench.manager.status(job))
        assert workbench.manager.status(job)['state'] in {'SUCCEEDED','PARTIAL_FAILURE'}, workbench.manager.status(job)
        document = workbench.document_read(document['id'])
        document = workbench.document_command(document['id'],'document.save',{},
            session_id=document['session_id'],expected_generation=document['generation'])['document']
        records.append((document,job))
    return records


def choose_source(monkeypatch, document):
    def select(parent,title,label,items,**kwargs):
        if title == '저장 자료 선택':
            candidates = [row for row in parent.client.documents()['documents']
                          if row.get('kind') in {'data', 'material', 'numerical', 'pde', 'simulation', 'evaluation'}]
            index = next(index for index, row in enumerate(candidates) if row['id'] == document['id'])
            return items[index], True
        return items[0], True
    monkeypatch.setattr(QInputDialog, 'getItem', select)


def test_pinned_analysis_picker_saved_reopen_and_actual_engine(app, workbench, retained_studies, monkeypatch, edit_windows):
    window = opened(app,workbench)
    original = deepcopy(window.edited_draft())
    window.operation.setCurrentIndex(window.operation.findData('analyze'))
    assert 'backend' not in window.edited_draft()['request']['inputs'] and not window.backend.isEnabled()
    training, job = retained_studies[0]
    choose_source(monkeypatch,training)
    window.choose_retained_result()
    wait(app, lambda:not window._busy and 'table' in window.edited_draft()['request']['inputs']['result_refs'])
    assert window.pinned_sources.rowCount() == 1
    window.choose_response_definition()
    assert window.declarations.rowCount() == 1
    edited = window.edited_draft()
    assert edited['request']['inputs']['responses'] == [{'response':'cost','unit':'MPa','component':'scalar','location':'model','reduction':'none'}]
    assert 'candidates' not in edited['request']['inputs'] and 'table' not in edited['request']['inputs']
    window.operation.setCurrentIndex(window.operation.findData('evaluate'))
    restored = window.edited_draft()
    assert restored['request'] == original['request'] and restored['source'] == original['source']
    assert restored['method_inputs'] == {'analyze': edited['request']['inputs']}
    window.operation.setCurrentIndex(window.operation.findData('analyze'))
    assert window.edited_draft()['request'] == edited['request']
    assert window.edited_draft()['method_inputs'] == {'evaluate': original['request']['inputs']}
    before = len(workbench.manager.list())
    window.save_document()
    wait(app,lambda:not window._busy and window.document.get('saved_revision'))
    assert not window.local_dirty, {'edited': window.edited_draft(), 'saved': window.document['draft']}
    assert len(workbench.manager.list()) == before
    other = RequestPlanWindow(InProcessClient(workbench),auto_open=False,poll_interval=0)
    other.open_document(document_id=window.document['id'])
    wait(app,lambda:other.document is not None and not other._busy)
    assert other.edited_draft()['request'] == edited['request']
    assert other.edited_draft()['method_inputs'] == {'evaluate': original['request']['inputs']}
    assert other.edited_draft()['source'] == edited['source']
    assert other.pinned_sources.rowCount() == other.declarations.rowCount() == 1
    other.operation.setCurrentIndex(other.operation.findData('evaluate'))
    assert other.edited_draft()['request'] == original['request']
    assert other.edited_draft()['method_inputs'] == {'analyze': edited['request']['inputs']}
    other.operation.setCurrentIndex(other.operation.findData('analyze'))
    assert other.edited_draft()['request'] == edited['request']
    assert other.edited_draft()['method_inputs'] == {'evaluate': original['request']['inputs']}
    # Returning to the exact saved request has no unapplied change.
    assert other.run_button.isEnabled() and not other.local_dirty
    other.apply_inputs()
    wait(app, lambda:not other._busy and not other.local_dirty)
    assert not other.document['diagnostics'] and len(workbench.manager.list()) == before
    other.run_button.click()
    wait(app,lambda:len(workbench.manager.list()) == before+1 and not other._busy)
    analysis_job = other.selected_job()
    wait(app,lambda:workbench.manager.status(analysis_job)['state'] in {'SUCCEEDED','FAILED'})
    assert workbench.manager.status(analysis_job)['state'] == 'SUCCEEDED'
    other.retry_result()
    wait(app,lambda:not other._busy and analysis_job in other._result_cache)
    result = other._result_cache[analysis_job]
    assert result['candidate_count'] == 6 and result['failure_count'] == 1
    assert result['statistics'][0]['count'] == 5
    assert other.figure.axes[0].get_ylabel() == '표준화 회귀계수 [1]'
    assert result['statistics'][0]['unit'] == 'MPa'


def test_surrogate_picker_requires_disjoint_retained_roles_and_keeps_typed_points(app,workbench,retained_studies,monkeypatch):
    window = opened(app,workbench)
    window.operation.setCurrentIndex(window.operation.findData('surrogate'))
    training, _ = retained_studies[0]
    choose_source(monkeypatch,training)
    window.choose_retained_result()
    wait(app,lambda:not window._busy and 'training' in window.edited_draft()['request']['inputs']['result_refs'])
    window.retained_role.setCurrentIndex(window.retained_role.findData('holdout'))
    window.choose_retained_result()
    wait(app,lambda:not window._busy)
    assert 'holdout' not in window.edited_draft()['request']['inputs']['result_refs']
    assert '서로 다른 계산 결과' in window.message.text()
    holdout, _ = retained_studies[1]
    choose_source(monkeypatch,holdout)
    window.choose_retained_result()
    wait(app,lambda:not window._busy and 'holdout' in window.edited_draft()['request']['inputs']['result_refs'])
    window.choose_response_definition()
    window._edit_structure(lambda inputs:inputs.update(points=[{'x':.25},{'x':1.1}]))
    assert window.pinned_sources.rowCount() == 2
    point = find_input(window,('points',0,'x'))
    point.setText(1,'unfinished prediction coordinate')
    assert window.edited_draft()['request']['inputs']['points'][0]['x'] == 'unfinished prediction coordinate'
    point.setText(1,'0.25')
    window.apply_inputs()
    wait(app,lambda:not window._busy and not window.local_dirty)
    assert not window.document['diagnostics']
    window.run_button.click()
    wait(app,lambda:not window._busy and window.selected_job() is not None)
    job = window.selected_job()
    wait(app,lambda:workbench.manager.status(job)['state'] in {'SUCCEEDED','FAILED'})
    assert workbench.manager.status(job)['state'] == 'SUCCEEDED'
    window.retry_result()
    wait(app,lambda:not window._busy and job in window._result_cache)
    result = window._result_cache[job]
    assert all(row['execution_status'] == 'PREDICTED' for row in result['predictions'])
    assert len(result['validation']['exclusions']['training']) == 1
    assert window.candidates.rowCount() == 2 and '예측' in window.figure.axes[0].get_ylabel()
    assert window.candidates.item(0,1).text() == '예측'
    assert not hasattr(window,'adopt_button')


def test_actual_retained_result_opens_expert_followup_without_provider_or_calculation(app,workbench,retained_studies,monkeypatch):
    from apps.research import desktop
    launched = []
    monkeypatch.setattr(desktop,'launch_tool',lambda client,tool,**kwargs:launched.append((tool,kwargs)) or {'status':'REQUESTED'})
    training, job = retained_studies[0]
    window = RequestPlanWindow(InProcessClient(workbench),auto_open=False,poll_interval=0)
    window.open_document(document_id=training['id'])
    wait(app,lambda:window.document is not None and not window._busy)
    before = len(workbench.manager.list())
    window.consult_expert()
    wait(app,lambda:not window._busy and len(launched) == 1)
    assert launched[0][0] == 'expert'
    expert = workbench.document_read(launched[0][1]['document_id'])
    assert expert['draft']['context']['selected_result_ids'] == [job]
    assert expert['draft']['context']['result_summary']['candidate_count'] == 6
    assert expert['draft']['composer']['evidence'][0]['job_id'] == job
    assert len(workbench.manager.list()) == before
    assert not expert['runs']


def run_edited_request(app, workbench, window):
    window.apply_inputs()
    wait(app, lambda:not window._busy and not window.local_dirty)
    assert not window.document['diagnostics'], window.document['diagnostics']
    before = len(workbench.manager.list())
    window.run_button.click()
    wait(app,lambda:not window._busy and len(workbench.manager.list()) == before+1)
    job = window.selected_job()
    wait(app,lambda:workbench.manager.status(job)['state'] in {'SUCCEEDED','PARTIAL_FAILURE','FAILED','REJECTED','CANCELLED'})
    assert workbench.manager.status(job)['state'] == 'SUCCEEDED', workbench.manager.status(job)
    window.retry_result()
    wait(app,lambda:not window._busy and job in window._result_cache)
    return job, window._result_cache[job]


def test_retained_batch_roles_execute_file_exchange_and_preserve_missing_rows(app,workbench,retained_studies,monkeypatch):
    window = opened(app,workbench)
    window.operation.setCurrentIndex(window.operation.findData('batch_export'))
    training, _ = retained_studies[0]
    choose_source(monkeypatch,training)
    window.choose_retained_result()
    wait(app,lambda:not window._busy and 'candidates' in window.edited_draft()['request']['inputs']['result_refs'])
    find_input(window,('case_id',)).setText(1,'DeclaredCase')
    job, exported = run_edited_request(app,workbench,window)
    assert exported['solver_execution'] == 'NOT_PERFORMED'
    manifest = exported['manifest']
    assert len(manifest['candidates']) == 6
    window.save_document()
    wait(app,lambda:not window._busy and window.document['runs'][-1].get('retention_complete'))
    batch_document = deepcopy(window.document)
    imported = RequestPlanWindow(InProcessClient(workbench),auto_open=False,poll_interval=0)
    imported.open_document(draft=request_draft({'purpose':'Recover actual exchanged rows','operation':'batch_import',
        'inputs':{'result_refs':{},'results':[]},'budget':{'evaluations':1}}))
    wait(app,lambda:imported.document is not None and not imported._busy)
    choose_source(monkeypatch,batch_document)
    imported.choose_retained_result()
    wait(app,lambda:not imported._busy and 'batch' in imported.edited_draft()['request']['inputs']['result_refs'])
    row = manifest['candidates'][0]
    actual = {'candidate_id':row['candidate_id'],'values':row['values'],'case_id':manifest['case_id'],
              'exchange_id':manifest['exchange_id'],'execution_status':'SUCCEEDED','responses':{'cost':{
                  'kind':'scalar','value':row['values']['x']**2,'unit':'MPa','component':'scalar','location':'model','reduction':'none'}}}
    imported._edit_structure(lambda inputs:inputs.update(results=[actual]))
    _, result = run_edited_request(app,workbench,imported)
    assert result['imported_count'] == 1 and result['missing_count'] == 5
    assert result['candidates'][0]['execution_status'] == 'SUCCEEDED'
    assert all(row['execution_status'] == 'NOT_EVALUATED' for row in result['candidates'][1:])
    assert 'backend' not in imported.edited_draft()['request']['inputs']


def test_sobol_sampling_request_is_editable_and_reports_optional_dependency(app,workbench):
    from importlib.util import find_spec
    window = opened(app,workbench)
    window.operation.setCurrentIndex(window.operation.findData('sample_sensitivity'))
    assert 'backend' not in window.edited_draft()['request']['inputs'] and not window.backend.isEnabled()
    variables = [{'id':'x','unit':'1','value':.5,'lower':0.,'upper':1.,'transform':'linear'}]
    window._edit_structure(lambda inputs:inputs.update(variables=variables))
    window.evaluations.setText('6')
    window.apply_inputs()
    wait(app,lambda:not window._busy and not window.local_dirty)
    assert not window.document['diagnostics']
    window.run_button.click()
    wait(app,lambda:not window._busy and window.selected_job() is not None)
    job = window.selected_job()
    wait(app,lambda:workbench.manager.status(job)['state'] in {'SUCCEEDED','FAILED'})
    if find_spec('SALib') is None:
        status = workbench.manager.status(job)
        assert status['state'] == 'FAILED' and 'SALib' in str(status.get('error'))
    else:
        result = workbench.document_result(window.document['id'],job)
        assert result['kind'] == 'sensitivity_plan' and result['solver_execution'] == 'NOT_PERFORMED'
        assert result['sampling']['method'] == 'SALib.sobol' and len(result['candidates']) == 6


def test_typed_leaf_structure_source_and_invalid_values_are_preserved(app, workbench, monkeypatch, edit_windows):
    window = opened(app, workbench)
    original = deepcopy(window.document['draft'])
    assert window.edited_draft() == original
    assert window.source.isReadOnly()
    modulus = find_input(window, ('settings', 'parameters', 'E'))
    modulus.setText(1, 'unfinished coefficient')
    assert window.edited_draft()['request']['inputs']['settings']['parameters']['E'] == 'unfinished coefficient'
    window.evaluations.setText('NaN')
    assert window.edited_draft()['request']['budget']['evaluations'] == 'NaN'
    window.apply_inputs()
    wait(app, lambda: not window._busy and not window.local_dirty)
    assert window.document['diagnostics'] and not window.run_button.isEnabled()
    assert not workbench.manager.list()
    window.undo_action.trigger()
    wait(app, lambda: not window._busy and window.edited_draft() == original)
    settings = find_input(window, ('settings',))
    window.inputs.setCurrentItem(settings)
    monkeypatch.setattr(QInputDialog, 'getItem', lambda *a, **kw: ('list', True))
    monkeypatch.setattr(QInputDialog, 'getText', lambda *a, **kw: ('notes', True))
    window.add_input()
    assert window.edited_draft()['request']['inputs']['settings']['notes'] == []
    notes = find_input(window, ('settings', 'notes'))
    window.inputs.setCurrentItem(notes)
    monkeypatch.setattr(QInputDialog, 'getItem', lambda *a, **kw: ('number', True))
    window.add_input()
    assert window.edited_draft()['request']['inputs']['settings']['notes'] == [0]
    window.inputs.setCurrentItem(find_input(window, ('settings', 'notes', 0)))
    window.remove_input()
    assert window.edited_draft()['request']['inputs']['settings']['notes'] == []
    assert window.edited_draft()['source'] == original['source']


def test_explicit_actual_evaluation_save_reopen_and_selected_result(app, workbench):
    window = opened(app, workbench)
    assert not workbench.manager.list()
    window.save_document()
    wait(app, lambda: not window._busy and window.document['saved_revision'] is not None)
    assert not workbench.manager.list()  # save never evaluates
    window.run_button.click()
    wait(app, lambda: len(workbench.manager.list()) == 1 and not window._busy)
    job = workbench.manager.list()[0]['id']
    wait(app, lambda: workbench.manager.status(job)['state'] == 'SUCCEEDED')
    window.retry_result()
    wait(app, lambda: not window._busy and job in window._result_cache)
    assert window._result_cache[job]['responses']['stress_xx']['value'][1] > 0
    assert window.responses.topLevelItemCount() > 0
    assert job in window.details.toPlainText()
    window.save_document()
    wait(app, lambda: not window._busy and window.document['runs'][0].get('retained_result') is not None)
    other = RequestPlanWindow(InProcessClient(workbench), auto_open=False, poll_interval=0)
    other.open_document(document_id=window.document['id'])
    wait(app, lambda: other.document is not None and not other._busy)
    assert other.edited_draft() == window.document['draft']
    assert len(workbench.manager.list()) == 1


def test_background_read_preserves_typed_edit_then_stale_conflict(app, workbench, edit_windows):
    window = opened(app, workbench)
    release = threading.Event()
    window.client.release = release
    window.refresh_document()
    assert window._busy and window._busy_background
    assert window.editor.isEnabled()
    window.purpose.setText('User edit while background request is in flight')
    window._edited()
    find_input(window, ('settings', 'parameters', 'E')).setText(1, '2500')
    release.set()
    wait(app, lambda: not window._busy)
    assert window.purpose.text() == 'User edit while background request is in flight'
    assert window.edited_draft()['request']['inputs']['settings']['parameters']['E'] == 2500
    current = workbench.document_read(window.document['id'])
    external = deepcopy(current['draft'])
    external['request']['purpose'] = 'External edit'
    workbench.document_command(current['id'], 'numerical.update', {'draft': external},
        session_id=current['session_id'], expected_generation=current['generation'], command_id='Cexternal')
    window.refresh_document()
    wait(app, lambda: not window._busy)
    assert window.conflict
    assert window.purpose.text() == 'User edit while background request is in flight'
    assert not window.run_button.isEnabled()


def test_request_chooser_uses_envelope_filters_material_bound_plans(app, workbench, monkeypatch):
    window = opened(app, workbench)
    draft = valid_request()
    draft['request']['purpose'] = '보완한 압력 비교 ' + '재료·구속·자중 유지 ' * 80
    other = workbench.document_open(kind='numerical', title='Exact request target', draft=draft)
    workbench.document_open(kind='numerical', title='Material-bound other editor')
    monkeypatch.setattr(window, '_leave', lambda callback: callback())
    def choose(parent, title, label, choices, **kwargs):
        assert not any('Material-bound' in item for item in choices)
        assert not any(other['id'] in item for item in choices)
        assert max(parent.fontMetrics().horizontalAdvance(item) for item in choices) < 700
        return next(item for item in choices if '보완한 압력 비교' in item), True
    monkeypatch.setattr(QInputDialog, 'getItem', choose)
    window.choose_document()
    wait(app, lambda: not window._busy and window.document['id'] == other['id'])
    assert window.document['title'] == 'Exact request target'


def _edit_sheet_cell(app, table, row, column, text):
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QLineEdit
    table.window().show()
    table.window().raise_()
    table.window().activateWindow()
    app.processEvents()
    table.scrollToItem(table.item(row, column))
    table.setCurrentCell(row, column)
    table.setFocus()
    QTest.keyClick(table, Qt.Key.Key_F2)
    app.processEvents()
    editor = QApplication.focusWidget()
    assert isinstance(editor, QLineEdit), type(editor)
    editor.selectAll()
    QTest.keyClicks(editor, text)
    QTest.keyClick(editor, Qt.Key.Key_Return)
    app.processEvents()


def test_generic_worksheet_precision_invalid_save_reopen_repair_and_method_options(app, workbench, retained_studies):
    original, _ = retained_studies[0]
    window = RequestPlanWindow(InProcessClient(workbench), auto_open=False, poll_interval=0)
    window.open_document(document_id=original['id'])
    wait(app, lambda: window.document is not None and not window._busy)
    assert window.input_tabs.currentWidget() is window.sheet
    assert window.variable_sheet.rowCount() == 1
    for raw in ('NaN', 'Infinity', '1e309', '1e'):
        _edit_sheet_cell(app, window.variable_sheet, 0, 2, raw)
        assert window.edited_draft()['request']['inputs']['variables'][0]['value'] == raw
        assert window._request_context() is not None  # Invalid values stay serializable.
    window.save_document()
    wait(app, lambda: not window._busy and not window.local_dirty and not window.document['dirty'])
    assert window.document['diagnostics'] and not window.run_button.isEnabled()
    other = RequestPlanWindow(InProcessClient(workbench), auto_open=False, poll_interval=0)
    other.open_document(document_id=window.document['id'])
    wait(app, lambda: other.document is not None and not other._busy)
    assert other.variable_sheet.item(0, 2).text() == '1e'
    _edit_sheet_cell(app, other.variable_sheet, 0, 2, '1.2e-5')
    other.apply_inputs()
    wait(app, lambda: not other._busy and not other.local_dirty)
    assert other.edited_draft()['request']['inputs']['variables'][0]['value'] == 1.2e-5
    assert other.run_button.isEnabled()
    other.undo_action.trigger()
    wait(app, lambda: not other._busy and other.variable_sheet.item(0, 2).text() == '1e')
    assert not other.run_button.isEnabled()
    other.redo_action.trigger()
    wait(app, lambda: not other._busy and other.edited_draft()['request']['inputs']['variables'][0]['value'] == 1.2e-5)
    other.operation.setCurrentIndex(other.operation.findData('optimize'))
    other._edit_structure(lambda value: value.update(
        objective={'response': 'cost', 'unit': 'MPa', 'reduction': 'none', 'direction': 'minimize'},
        constraints=[{'response': 'cost', 'unit': 'MPa', 'reduction': 'none', 'operator': '<=', 'limit': .5}],
        options={'max_generations': 2, 'population_size': 5, 'future_option': {'authored': 'preserve'}}))
    _edit_sheet_cell(app, other.response_sheet, 1, 4, '-1.2e-5')
    assert other.edited_draft()['request']['inputs']['constraints'][0]['limit'] == -1.2e-5
    other.operation.setCurrentIndex(other.operation.findData('doe'))
    assert other.variable_sheet.item(0, 2).text() == '1.2e-05'
    other.operation.setCurrentIndex(other.operation.findData('optimize'))
    assert other.edited_draft()['request']['inputs']['options']['future_option'] == {'authored': 'preserve'}
    assert other.response_sheet.item(1, 4).text() == '-1.2e-05'
    other.variable_sheet.selectRow(0)
    other.remove_sheet_variables()
    assert other.edited_draft()['request']['inputs']['variables'] == []
    for view in (window, other):
        view._allow_close = True
        view.close()


def test_generic_worksheet_malformed_ids_and_retained_doe_controls(app, workbench, retained_studies):
    from caelab.storage import canonical_hash
    document, job = retained_studies[0]
    window = RequestPlanWindow(InProcessClient(workbench), auto_open=False, poll_interval=0)
    draft = deepcopy(document['draft'])
    draft['request']['inputs']['variables'][0]['id'] = {'invalid': ['preserve']}
    window.open_document(draft=draft)
    wait(app, lambda: window.document is not None and not window._busy)
    assert not window._populating
    assert window.edited_draft() == draft
    assert not window.run_button.isEnabled()
    reference = workbench.document_result_reference(document['id'], job)
    valid = deepcopy(document['draft']['request']['inputs'])
    valid.pop('candidates', None)
    valid.pop('count', None)
    valid.pop('seed', None)
    valid['result_refs'] = {'candidates': reference}
    window._edit_structure(lambda value: (value.clear(), value.update(valid)))
    assert window.method_sheet.rowCount() == 0
    assert canonical_hash(window.edited_draft())
    window.apply_inputs()
    wait(app, lambda: not window._busy)
    assert not window.document['diagnostics']
    window._allow_close = True
    window.close()


def test_generic_doe_actual_candidate_scalar_pick_and_retained_curve(app, workbench, monkeypatch):
    from types import SimpleNamespace
    from caelab.backends import Backend, _registry
    calls = []
    def model(values, settings):
        x = values['x']
        calls.append(x)
        if x > .9:
            return {'execution_status': 'FAILED', 'responses': {}, 'diagnostics': {'failure_reason': 'Declared test domain'}}
        identity = {'unit': 'MPa', 'component': 'scalar', 'location': 'model', 'frame': 'test_frame', 'measure': 'test_response'}
        return {'execution_status': 'SUCCEEDED', 'responses': {
            'cost': {'kind': 'scalar', 'value': x*x, **identity},
            'trace': {'kind': 'series', 'value': [x, 2*x, 4*x], **identity,
                      'axes': [{'name': 'time', 'unit': 's', 'values': [0., .25, 2.]}]}}}
    monkeypatch.setitem(_registry, 'test.worksheet.numeric', Backend('test.worksheet.numeric', ('prepared',), lambda: model))
    draft = request_draft({'purpose': 'Actual small DOE engine / algebraic test evaluator', 'operation': 'doe',
        'inputs': {'backend': 'test.worksheet.numeric',
                   'variables': [{'id': 'x', 'unit': '1', 'value': .5, 'lower': 0., 'upper': 1.}],
                   'candidates': [{'candidate_id': 'Cfirst', 'values': {'x': .2}},
                                  {'candidate_id': 'Cfailed', 'values': {'x': .95}},
                                  {'candidate_id': 'Clast', 'values': {'x': .8}}]},
        'budget': {'evaluations': 3}})
    window = RequestPlanWindow(InProcessClient(workbench), auto_open=False, poll_interval=0)
    window.open_document(draft=draft)
    wait(app, lambda: window.document is not None and not window._busy)
    window.run_button.click()
    wait(app, lambda: not window._busy and window.selected_job() is not None)
    job = window.selected_job()
    wait(app, lambda: workbench.manager.status(job)['state'] in {'SUCCEEDED', 'PARTIAL_FAILURE', 'FAILED'})
    window.retry_result()
    wait(app, lambda: not window._busy and job in window._result_cache)
    assert calls == [.2, .95, .8]
    result = window._result_cache[job]
    assert [row['candidate_id'] for row in result['candidates']] == ['Cfirst', 'Cfailed', 'Clast']
    assert result['candidates'][1]['execution_status'] == 'FAILED'
    window.plot_response.setCurrentIndex(window.plot_response.findData({'candidate_response': 'cost'}))
    artist = window.figure.axes[0].collections[0]
    assert artist.get_offsets().tolist() == [[0., .2*.2], [2., .8*.8]]
    window._candidate_plot_picked(SimpleNamespace(artist=artist, ind=[1]))
    assert window._selected_actual_candidate()['candidate_id'] == 'Clast'
    window.plot_response.setCurrentIndex(window.plot_response.findData({'candidate_response': 'trace'}))
    line = window.figure.axes[0].lines[0]
    assert list(line.get_xdata()) == [0., .25, 2.]
    assert list(line.get_ydata()) == [.8, 1.6, 3.2]
    retained_curve = result['candidates'][2]['responses']['trace']
    assert list(line.get_xdata()) == retained_curve['axes'][0]['values']
    assert list(line.get_ydata()) == retained_curve['value']
    assert window.figure.axes[0].get_xlabel() == '시간 [s]'
    assert window.figure.axes[0].get_ylabel() == 'trace [MPa]'
    window.candidates.selectRow(1)
    assert not window.figure.axes[0].lines
    assert window._selected_actual_candidate()['candidate_id'] == 'Cfailed'
    window.save_document()
    wait(app, lambda: not window._busy and window.document['runs'][0].get('retention_complete'))
    assert workbench.document_result_reference(window.document['id'], job)['result_sha256']
    window._allow_close = True
    window.close()


def test_generic_optimize_worksheet_runs_existing_engine_with_physical_constraint(app, workbench, retained_studies):
    document, _ = retained_studies[0]
    draft = deepcopy(document['draft'])
    inputs = draft['request']['inputs']
    inputs.pop('candidates', None)
    inputs.pop('count', None)
    inputs.update(objective={'response': 'cost', 'unit': 'MPa', 'component': 'scalar', 'location': 'model',
                             'reduction': 'none', 'direction': 'minimize'},
                  constraints=[{'response': 'cost', 'unit': 'MPa', 'component': 'scalar', 'location': 'model',
                                'reduction': 'none', 'operator': '<=', 'limit': .7}],
                  options={'max_generations': 1, 'population_size': 5, 'retain_responses': 'all'})
    draft['request']['operation'] = 'optimize'
    draft['request']['budget']['evaluations'] = 20
    window = RequestPlanWindow(InProcessClient(workbench), auto_open=False, poll_interval=0)
    window.open_document(draft=draft)
    wait(app, lambda: window.document is not None and not window._busy)
    assert window.response_sheet.rowCount() == 2 and window.method_sheet.rowCount() == 5
    assert window.method_sheet.item(0, 0).text() == '최적화 방법'
    _edit_sheet_cell(app, window.response_sheet, 1, 4, '6e-1')
    _, result = run_edited_request(app, workbench, window)
    assert result['kind'] == 'optimization'
    assert result['constraint_definitions'][0]['limit'] == .6
    assert 0 < len(result['candidates']) <= 20
    for row in result['candidates']:
        if row['execution_status'] == 'SUCCEEDED':
            assert row['objective'] == pytest.approx(row['values']['x'] ** 2)
        else:
            assert row.get('objective') is None
    assert result['best']['feasible']
    window._allow_close = True
    window.close()
