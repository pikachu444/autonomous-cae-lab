"""Actual Qt request editor and actual Numerical owner/evaluator checks.

No provider is used: request Plans execute the existing FELUPE calculation only
when Run is clicked. A separate transport latency double checks callback races.
"""
import os
os.environ['QT_QPA_PLATFORM'] = 'offscreen'
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
    raise AssertionError('request Plan Qt callback did not settle')


def valid_request():
    return request_draft({'purpose': 'Evaluate the actual material point', 'operation': 'evaluate',
        'inputs': material_draft(), 'budget': {'evaluations': 1}})


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
        if title.startswith('Select retained '):
            return next(item for item in items if document['id'] in item), True
        return items[0], True
    monkeypatch.setattr(QInputDialog, 'getItem', select)


def test_pinned_analysis_picker_saved_reopen_and_actual_engine(app, workbench, retained_studies, monkeypatch):
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
    assert window.edited_draft() == original
    window.operation.setCurrentIndex(window.operation.findData('analyze'))
    assert window.edited_draft() == edited
    before = len(workbench.manager.list())
    window.save_document()
    wait(app,lambda:not window._busy and not window.local_dirty and window.document.get('saved_revision'))
    assert len(workbench.manager.list()) == before
    other = RequestPlanWindow(InProcessClient(workbench),auto_open=False,poll_interval=0)
    other.open_document(document_id=window.document['id'])
    wait(app,lambda:other.document is not None and not other._busy)
    assert other.edited_draft() == edited
    assert other.pinned_sources.rowCount() == other.declarations.rowCount() == 1
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
    assert other.figure.axes[0].get_ylabel() == 'mean ± sample std [MPa]'


def test_surrogate_picker_requires_disjoint_retained_roles_and_keeps_typed_points(app,workbench,retained_studies,monkeypatch):
    window = opened(app,workbench)
    window.operation.setCurrentIndex(window.operation.findData('surrogate'))
    training, _ = retained_studies[0]
    choose_source(monkeypatch,training)
    window.choose_retained_result()
    wait(app,lambda:not window._busy and 'training' in window.edited_draft()['request']['inputs']['result_refs'])
    window.retained_role.setCurrentText('holdout')
    window.choose_retained_result()
    wait(app,lambda:not window._busy)
    assert 'holdout' not in window.edited_draft()['request']['inputs']['result_refs']
    assert 'distinct retained' in window.message.text()
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
    assert window.candidates.rowCount() == 2 and 'PREDICTED' in window.figure.axes[0].get_ylabel()
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


def test_typed_leaf_structure_source_and_invalid_values_are_preserved(app, workbench, monkeypatch):
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


def test_background_read_preserves_typed_edit_then_stale_conflict(app, workbench):
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
    other = workbench.document_open(kind='numerical', title='Exact request target', draft=valid_request())
    workbench.document_open(kind='numerical', title='Material-bound other editor')
    monkeypatch.setattr(window, '_leave', lambda callback: callback())
    def choose(parent, title, label, choices, **kwargs):
        assert not any('Material-bound' in item for item in choices)
        return next(item for item in choices if other['id'] in item), True
    monkeypatch.setattr(QInputDialog, 'getItem', choose)
    window.choose_document()
    wait(app, lambda: not window._busy and window.document['id'] == other['id'])
    assert window.document['title'] == 'Exact request target'
