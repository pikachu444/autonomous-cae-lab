"""Focused real Qt + real owners; algebra is an explicit test-only evaluator."""
import os
os.environ['QT_QPA_PLATFORM']='offscreen'
from copy import deepcopy
from types import SimpleNamespace
import time
import pytest
pytest.importorskip('PySide6')
pytest.importorskip('scipy')
from PySide6.QtCore import QThreadPool,Qt
from PySide6.QtWidgets import QApplication,QInputDialog,QMessageBox,QStyleOptionViewItem,QDialog,QTableWidget
from apps.research.request_plan_window import RequestPlanWindow
from apps.research.numerical_methods import MethodDialog
from caelab.workbench import Workbench
from caelab.numerical_document import request_draft
from caelab.material_document import default_draft
from caelab.backends import Backend,_registry


class Client:
    """In-process transport only; owner, jobs and numerical calculations are real."""
    def __init__(self,wb):self.wb=wb
    def __getattr__(self,name):return getattr(self.wb,name)
    def status(self,identifier):return self.wb.manager.status(identifier)


def wait(app,predicate,window=None):
    deadline=time.monotonic()+10
    while time.monotonic()<deadline:
        app.processEvents()
        if predicate():return
        time.sleep(.005)
    raise AssertionError(window.message.text() if window else 'Qt callback did not settle')


@pytest.fixture
def environment(tmp_path):
    app=QApplication.instance() or QApplication([])
    from apps.research.appearance import apply_appearance
    apply_appearance(app)
    wb=Workbench(tmp_path)
    windows=[]
    def open_window(draft=None,identifier=None):
        w=RequestPlanWindow(Client(wb),auto_open=False,poll_interval=0)
        windows.append(w);w.show()
        w.open_document(document_id=identifier,draft=draft)
        wait(app,lambda:w.document is not None and not w._busy,w)
        return w
    yield app,wb,open_window
    for w in windows:
        w.timer.stop()
        wait(app,lambda:not w._busy and not w._callbacks,w)
        w._allow_close=True;w.close()
    assert QThreadPool.globalInstance().waitForDone(3000)
    app.processEvents()
    assert wb.shutdown()['joined']
    for w in windows:w.deleteLater()
    app.processEvents()


def request(operation,inputs,budget=32):
    return request_draft({'purpose':'공개 수치 연구','operation':operation,
                          'inputs':inputs,'budget':{'evaluations':budget}})


def inputs():
    return {'backend':'test.d6.ui','settings':{},
        'variables':[dict(id='x',unit='1',value=.5,lower=0.,upper=1.,transform='linear')],
        'distributions':{'x':dict(distribution='uniform',unit='1',lower=0.,upper=1.)},
        'source':dict(origin='SYNTHETIC',reference='Public algebra; not engineering evidence'),
        'independence':'INDEPENDENT_USER_DECLARED','count':32,'seed':4,
        'thresholds':[dict(response='cost',unit='MPa',reduction='none',component='scalar',location='model',limit=.25,operator='>')]}


def install_algebra(monkeypatch):
    def evaluate(values,settings):
        x=values['x']
        if settings.get('fail') and x>.75:
            return {'execution_status':'FAILED','responses':{},'diagnostics':{'failure_reason':'Declared failure'}}
        return {'execution_status':'SUCCEEDED','responses':{'cost':{
            'kind':'scalar','value':settings.get('factor',1)*x*x,'unit':'MPa','component':'scalar','location':'model','reduction':'none'}}}
    monkeypatch.setitem(_registry,'test.d6.ui',Backend('test.d6.ui',('prepared',),lambda:evaluate))


def save(app,w):
    wait(app,lambda:not w._busy and not w._callbacks and not getattr(w,'_retained_labels_scheduled',False),w)
    w.save_document()
    wait(app,lambda:not w._busy and not w.local_dirty and bool(w.document.get('saved_revision')),w)


def execute(app,wb,w):
    wait(app,lambda:not w._busy and not w._callbacks and not getattr(w,'_retained_labels_scheduled',False),w)
    if w.local_dirty:
        w.apply_inputs();wait(app,lambda:not w._busy and not w.local_dirty,w)
    assert not w.document['diagnostics'],w.document['diagnostics']
    before=len(wb.manager.list())
    w.run_button.click()
    wait(app,lambda:len(wb.manager.list())==before+1 and not w._busy,w)
    job=w.selected_job()
    wait(app,lambda:wb.manager.status(job)['state'] in {'SUCCEEDED','FAILED','PARTIAL_FAILURE','REJECTED'},w)
    assert wb.manager.status(job)['state'] in {'SUCCEEDED','PARTIAL_FAILURE'},wb.manager.status(job)
    w.retry_result();wait(app,lambda:not w._busy and job in w._result_cache,w)
    return job,w._result_cache[job]


def test_distribution_draft_cancel_partial_save_reopen_repair(environment,monkeypatch):
    app,wb,open_window=environment
    install_algebra(monkeypatch)
    value=inputs();value['distributions']['x']['operator_note']='keep extension'
    w=open_window(request('uq',value))
    before=deepcopy(w.edited_draft())
    d=MethodDialog(w,value,'uq')
    d.tables[0].item(0,4).setText('1e')
    d.reject()
    assert w.edited_draft()==before
    edited=d.value()
    assert edited['distributions']['x']['std']=='1e'
    assert edited['distributions']['x']['operator_note']=='keep extension'
    # Required count partial text blocks execution but is an ordinary saved draft.
    w.method_sheet.item(0,1).setText('1e')
    save(app,w)
    assert w.document['diagnostics'] and not w.run_button.isEnabled()
    reopened=open_window(identifier=w.document['id'])
    assert reopened.method_sheet.item(0,1).text()=='1e'
    reopened.method_sheet.item(0,1).setText('32')
    save(app,reopened)
    assert not reopened.document['diagnostics']
    reopened.undo_action.trigger()
    wait(app,lambda:not reopened._busy and reopened.method_sheet.item(0,1).text()=='1e',reopened)
    reopened.redo_action.trigger()
    wait(app,lambda:not reopened._busy and reopened.method_sheet.item(0,1).text()=='32',reopened)
    assert wb.manager.list()==[]


def test_actual_uq_linked_rows_full_width_and_late_read_preserves_edit(environment,monkeypatch):
    app,wb,open_window=environment
    install_algebra(monkeypatch)
    value=inputs();value['settings']['fail']=True
    w=open_window(request('uq',value))
    job,result=execute(app,wb,w)
    w.work_pages.setCurrentWidget(w.results_panel)
    assert '전체 32 / 유효 24' in w.result_summary.text()
    assert format(8/24,'.6g') in w.result_summary.text() and format(8/32,'.6g') in w.result_summary.text()
    assert result['probability_statistics'][0]['exceedance_fraction_valid']==8/24
    artist=w.figure.axes[0].collections[0]
    identifier=artist._candidate_ids[4]
    w._candidate_plot_picked(SimpleNamespace(artist=artist,ind=[4]))
    assert w._selected_actual_candidate()['candidate_id']==identifier
    for size in ((1100,780),(1440,900)):
        w.resize(*size);app.processEvents()
        assert w.width()==size[0] and w.height()==size[1]
        assert w.canvas.width()>700
        assert w.canvas.height()>170
    w._edit_structure(lambda current:current['thresholds'][0].update(unit='Pa'))
    draft=deepcopy(w.edited_draft())
    w._draw_result()  # A result callback only redraws the frozen run.
    assert w.edited_draft()==draft and w.work_pages.currentWidget() is w.results_panel
    assert w._selected_actual_candidate()['candidate_id']==identifier
    assert '[MPa]' in w.figure.axes[0].get_xlabel()
    assert result['probability_statistics'][0]['threshold']['unit']=='MPa'
    w._result_cache.pop(job)
    w._draw_result()
    assert not w.result_summary.text()


def test_independent_plan_selects_real_saved_material_and_runs_existing_adapter(environment,monkeypatch):
    pytest.importorskip('felupe')
    app,wb,open_window=environment
    model=wb.document_open(kind='material',title='공개 탄성 시험',draft=default_draft())
    model=wb.document_command(model['id'],'document.save',{},session_id=model['session_id'],
        expected_generation=model['generation'])['document']
    first=model
    model=wb.document_open(kind='material',title='같은 설정 B',draft=deepcopy(first['draft']))
    model=wb.document_command(model['id'],'document.save',{},session_id=model['session_id'],
        expected_generation=model['generation'])['document']
    model_before=deepcopy(model['draft'])
    w=open_window(request('doe',{'backend':'','settings':{},'variables':[],'count':2,'seed':4},2))
    selected_title=[first['title']]
    monkeypatch.setattr(QInputDialog,'getItem',lambda parent,title,label,items,**kwargs:
        (next(item for item in items if selected_title[0] in item),True))
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.StandardButton.Yes)
    w.choose_model_document()
    wait(app,lambda:not w._busy and w.edited_draft().get('model_source',{}).get('document_id')==first['id'],w)
    selected_title[0]=model['title']
    w.choose_model_document()
    wait(app,lambda:not w._busy and w.edited_draft().get('model_source',{}).get('document_id')==model['id'],w)
    from apps.research import desktop
    opened=[]
    monkeypatch.setattr(desktop,'launch_tool',lambda client,tool,**kwargs:
        (opened.append((tool,kwargs['document_id'])) or {'status':'OPENED'}))
    w.open_model_source();wait(app,lambda:not w._busy and len(opened)==1,w)
    w.open_source();wait(app,lambda:not w._busy and len(opened)==2,w)
    assert opened==[('material',model['id']),('material',model['id'])]
    reads=[]
    original_read=w.client.document_read
    monkeypatch.setattr(w.client,'document_read',lambda identifier:
        (reads.append(identifier) or original_read(identifier)))
    w._pick_retained_curve(lambda *args:pytest.fail('No retained model run yet'),model=True)
    wait(app,lambda:not w._busy and bool(reads),w)
    assert reads==[model['id']]
    monkeypatch.setattr(w,'_select_model_variables',lambda rows:[row for row in rows if row['id']=='E'])
    w.choose_model_variables()
    wait(app,lambda:not w._busy and w.variable_sheet.rowCount()==1,w)
    assert w.variable_sheet.item(0,0).text()=='탄성계수'
    assert w.edited_draft()['source']['document_id']==model['id']
    job,result=execute(app,wb,w)
    assert len(result['candidates'])==2
    previews=[]
    monkeypatch.setattr(w,'_review_pde_changes',lambda preview:(previews.append(deepcopy(preview)) or False))
    w.candidates.selectRow(0);app.processEvents()
    w.review_pde_candidate()
    wait(app,lambda:not w._busy and bool(previews),w)
    assert previews[0]['target_document_id']==model['id']
    assert previews[0]['source']==w.edited_draft()['model_source']
    assert wb.document_read(first['id'])['draft']==model_before
    assert all(row['execution_status']=='SUCCEEDED' for row in result['candidates'])
    assert result['candidates'][0]['responses']['stress_xx']['unit']==model_before['settings']['stress_unit']
    save(app,w)
    reopened=open_window(identifier=w.document['id'])
    assert reopened.document['runs'][-1]['job_id']==job
    assert reopened.edited_draft()['model_source']['document_id']==model['id']
    assert wb.document_read(model['id'])['draft']==model_before
    # Explicit adoption uses the same reviewed actual B candidate; no new solve.
    reopened.retry_result();wait(app,lambda:not reopened._busy and job in reopened._result_cache,reopened)
    reopened.candidates.selectRow(0);app.processEvents()
    monkeypatch.setattr(reopened,'_review_pde_changes',lambda preview:True)
    jobs=len(wb.manager.list())
    reopened.review_pde_candidate()
    expected=deepcopy(model_before)
    expected['settings']['parameters'].update(result['candidates'][0]['values'])
    wait(app,lambda:not reopened._busy and wb.document_read(model['id'])['draft']==expected,reopened)
    assert wb.document_read(first['id'])['draft']==model_before
    adopted=wb.document_read(model['id'])
    assert adopted['input_revision']!=model['input_revision'] and adopted['dirty']
    adopted=wb.document_command(adopted['id'],'document.save',{},session_id=adopted['session_id'],
        expected_generation=adopted['generation'])['document']
    assert adopted['saved_revision']!=model['saved_revision'] and not adopted['dirty']
    assert len(wb.manager.list())==jobs


def test_changed_variable_list_cannot_relabel_retained_correlation(environment):
    app,wb,open_window=environment
    value=inputs()
    value['variables']=[dict(value['variables'][0],id=name) for name in ('a','c')]
    value['correlation']={'variables':['a','b','c'],
        'matrix':[[1.,.8,.2],[.8,1.,.4],[.2,.4,1.]]}
    value['independence']='CORRELATED_NORMAL_USER_DECLARED'
    w=open_window(request('uq',value))
    dialog=MethodDialog(w,value,'uq')
    assert dialog.correlation_table.item(0,2).text()==''  # must not show old a-b=.8 as a-c
    assert dialog.value()['correlation']==value['correlation']
    for i,row in enumerate([[1.,.25],[.25,1.]]):
        for j,item in enumerate(row):dialog.correlation_table.item(i,j+1).setText(str(item))
    assert dialog.value()['correlation']=={'variables':['a','c'],'matrix':[[1.,.25],[.25,1.]]}
    dialog.reject()
    assert w.edited_draft()['request']['inputs']['correlation']==value['correlation']


def test_model_trial_cancel_is_atomic_and_primary_limits_keep_identity(environment,monkeypatch):
    app,wb,open_window=environment
    model=wb.document_open(kind='material',title='실제 재료',draft=default_draft())
    model=wb.document_command(model['id'],'document.save',{},session_id=model['session_id'],
        expected_generation=model['generation'])['document']
    trials=[dict(id=name,response='stress_xx',settings={'sentinel':name}) for name in ('A','B')]
    w=open_window(request('fit',{'backend':'','variables':[],'experiments':trials}))
    before=deepcopy(w.edited_draft())
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.StandardButton.Yes)
    def choose(parent,title,label,items,**kwargs):
        return (items[0],title!='Use model protocol')
    monkeypatch.setattr(QInputDialog,'getItem',choose)
    w.choose_model_document();wait(app,lambda:not w._busy,w)
    assert w.edited_draft()==before and not w.local_dirty
    monkeypatch.setattr(QInputDialog,'getItem',lambda parent,title,label,items,**kwargs:(items[0],True))
    w.choose_model_document()
    wait(app,lambda:not w._busy and w.local_dirty,w)
    assert w.edited_draft()['source']['document_id']==model['id']
    got=w.edited_draft()['request']['inputs']
    assert got['experiments'][0]['settings']==model['draft']['settings']
    assert got['experiments'][1]['settings']=={'sentinel':'B'}
    from apps.research.numerical_methods import remap_thresholds
    old={'objectives':[{'response':n,'unit':'N'} for n in ('A','B','C')],
         'primary_index':0,'threshold_grid':[[10.],[100.]]}
    changed=deepcopy(old);changed['primary_index']=2
    remap_thresholds(old,changed)
    assert changed['threshold_grid']==[[],[10.]]  # no old B limit silently becomes A
    removed=deepcopy(old);removed['objectives'].pop(1)
    remap_thresholds(old,removed)
    assert removed['threshold_grid']==[[100.]]



@pytest.mark.parametrize('kind',['expert','study'])
def test_selected_model_preserves_return_origin_and_saved_exact_reference(environment,monkeypatch,kind):
    app,wb,open_window=environment
    from caelab.storage import canonical_hash
    model=wb.document_open(kind='material',title='평가 모델',draft=default_draft())
    model=wb.document_command(model['id'],'document.save',{},session_id=model['session_id'],
        expected_generation=model['generation'])['document']
    # These exact-shape origin references exercise editor preservation only;
    # no round, provider or fabricated result is executed.
    origin=({'discussion_id':'Xorigin','turn_id':'Tturn','proposal_index':0,'job_id':'Jorigin',
        'input_revision':'Rorigin','input_sha256':'a'*64,'proposal_sha256':'b'*64} if kind=='expert' else
        {'document_id':'Sorigin','kind':'study','saved_revision':'Rsave','input_revision':'Rinput','input_sha256':'a'*64})
    draft=request('doe',{'backend':'','settings':{},'variables':[],'count':2},2)
    draft['source']=origin
    w=open_window(draft)
    monkeypatch.setattr(QInputDialog,'getItem',lambda parent,title,label,items,**kwargs:(items[0],True))
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.StandardButton.Yes)
    w.choose_model_document()
    wait(app,lambda:not w._busy and w.edited_draft().get('model_source',{}).get('document_id')==model['id'],w)
    assert w.edited_draft()['source']==origin
    assert w.edited_draft()['model_source']['input_sha256']==canonical_hash(model['draft'])
    save(app,w)
    reopened=open_window(identifier=w.document['id'])
    assert reopened.edited_draft()['source']==origin
    assert reopened.edited_draft()['model_source']==w.edited_draft()['model_source']
    assert wb.manager.list()==[]


def test_method_choices_display_labels_keep_canonical_unknown_and_objective_identity(environment):
    app,wb,open_window=environment
    w=open_window(request('uq',inputs()))
    assert w.method_sheet.item(2,1).text()=='독립 분포'
    assert w.method_sheet.item(3,1).text()=='합성 예제'
    index=w.method_sheet.model().index(2,1)
    delegate=w.method_sheet.itemDelegate()
    editor=delegate.createEditor(w.method_sheet,QStyleOptionViewItem(),index)
    delegate.setEditorData(editor,index)
    assert editor.currentData()=='INDEPENDENT_USER_DECLARED'
    editor.setCurrentIndex(editor.findData('CORRELATED_NORMAL_USER_DECLARED'))
    delegate.setModelData(editor,w.method_sheet.model(),index)
    assert w.method_sheet.item(2,1).text()=='상관 정규분포'
    assert w.edited_draft()['request']['inputs']['independence']=='CORRELATED_NORMAL_USER_DECLARED'
    w.method_sheet.item(2,1).setText('FUTURE_CORRELATION')
    save(app,w)
    reopened=open_window(identifier=w.document['id'])
    assert reopened.method_sheet.item(2,1).text()=='FUTURE_CORRELATION'
    assert reopened.edited_draft()['request']['inputs']['independence']=='FUTURE_CORRELATION'
    sobol=open_window(request('sample_sensitivity',{'variables':inputs()['variables'],'count':2,'second_order':False}))
    assert sobol.method_sheet.item(2,1).text()=='포함하지 않음'
    sobol.method_sheet.item(2,1).setText('포함')
    assert sobol.edited_draft()['request']['inputs']['second_order'] is True
    objectives=[dict(response=n,unit='N',direction='minimize',component='scalar',reduction='none') for n in ('A','B','C')]
    value={'backend':'test.d6.ui','settings':{},'variables':inputs()['variables'],
        'objectives':objectives,'primary_index':0,'threshold_grid':[[10.],[100.]],'total_evaluation_budget':10}
    multi=open_window(request('epsilon',value,10))
    item=multi.method_sheet.item(0,1)
    assert item.text()=='A [N] 최소화' and multi.method_sheet.item(0,0).text()=='주 목표'
    index=multi.method_sheet.model().index(0,1)
    delegate=multi.method_sheet.itemDelegate()
    editor=delegate.createEditor(multi.method_sheet,QStyleOptionViewItem(),index)
    delegate.setEditorData(editor,index);editor.setCurrentIndex(editor.findData(2))
    delegate.setModelData(editor,multi.method_sheet.model(),index)
    app.processEvents()
    got=multi.edited_draft()['request']['inputs']
    assert got['primary_index']==2 and got['threshold_grid']==[[],[10.]]
    assert multi.method_sheet.item(0,1).text()=='C [N] 최소화'
    assert wb.manager.list()==[]



def test_saved_model_search_worksheet_reopen_and_exact_readable_sources(environment,monkeypatch):
    app,wb,open_window=environment
    install_algebra(monkeypatch);refs=[]
    for points in ((0.,.2,.4,.6,.8,1.),(.1,.3,.5,.7,.9)):
        w=open_window(request('doe',{'backend':'test.d6.ui','settings':{},'variables':inputs()['variables'],
            'candidates':[{'values':{'x':x}} for x in points]},len(points)))
        job,_=execute(app,wb,w);save(app,w)
        refs.append(wb.document_result_reference(w.document['id'],job))
    definition=dict(response='cost',unit='MPa',component='scalar',location='model',reduction='none')
    model=open_window(request('surrogate',{'result_refs':dict(zip(('training','holdout'),refs)),
        'response':definition,'points':[],'options':{'neighbors':3}}))
    job,result=execute(app,wb,model);save(app,model)
    reference=wb.document_result_reference(model.document['id'],job)
    search={'variables':deepcopy(result['variables']),'objective':dict(definition,direction='minimize'),
        'constraints':[dict(definition,operator='<=',limit=.9)],'seed':5,'options':{'max_generations':1,'population_size':5}}
    w=open_window(request('surrogate',{'result_refs':{'model':reference},'search':search},10))
    wait(app,lambda:not w._busy and not w._callbacks and not getattr(w,'_retained_labels_scheduled',False),w)
    assert w.variable_sheet.rowCount()==1 and w.response_sheet.rowCount()==2
    assert w.variable_sheet.item(0,0).text()=='x' and w.response_sheet.item(0,1).text()=='cost'
    label=w.pinned_sources.item(0,1)
    label_text=label.text()
    assert model.document['title'] in label.text() and '계산 1' in label.text()
    assert reference['job_id'] not in label.text() and reference['job_id'] in label.toolTip()
    assert w.pinned_sources.isColumnHidden(2) and w.pinned_sources.isColumnHidden(3)
    w.variable_sheet.item(0,3).setText('0.1');w.response_sheet.item(1,4).setText('0.8')
    assert w.edited_draft()['request']['inputs']['search']['variables'][0]['lower']==.1
    assert w.edited_draft()['request']['inputs']['search']['constraints'][0]['limit']==.8
    save(app,w)
    reopened=open_window(identifier=w.document['id'])
    wait(app,lambda:not reopened._busy and not reopened._callbacks and not getattr(reopened,'_retained_labels_scheduled',False),reopened)
    assert reopened.pinned_sources.item(0,1).text()==label_text
    assert reopened.edited_draft()['request']['inputs']['search']['constraints'][0]['limit']==.8
    for operation,model_hidden,constraint_hidden in (('doe',False,True),('uq',False,False),('sample_sensitivity',True,True)):
        reopened.operation.setCurrentIndex(reopened.operation.findData(operation))
        assert reopened.model_response_button.isHidden()==model_hidden
        assert reopened.constraint_button.isHidden()==constraint_hidden
        assert not reopened.variables_button.isHidden() and not reopened.variable_domains_button.isHidden()
    reopened.operation.setCurrentIndex(reopened.operation.findData('surrogate'))
    assert reopened.variables_button.isHidden() and reopened.model_response_button.isHidden()
    assert reopened.edited_draft()['request']['inputs']['search']['constraints'][0]['limit']==.8
    jobs=len(wb.manager.list())
    # A different variable meaning remains literal, saveable and blocked by the existing search admission.
    reopened._edit_structure(lambda value:value['search']['variables'][0].update(unit='Pa'))
    save(app,reopened)
    reply=wb.document_command(reopened.document['id'],'numerical.run',{},session_id=reopened.document['session_id'],
        expected_generation=reopened.document['generation'])
    wrong=reply['job']['id'];wait(app,lambda:wb.manager.status(wrong)['state']=='FAILED',reopened)
    assert 'units' in wb.manager.status(wrong)['error']['message']
    assert len(wb.manager.list())==jobs+1 and wb.document_result(model.document['id'],job)==result


def test_saved_prediction_to_explicit_actual_confirmation_and_paired_read(environment,monkeypatch):
    app,wb,open_window=environment
    install_algebra(monkeypatch)
    refs=[]
    for points in ((0.,.5,1.),(.25,.75)):
        w=open_window(request('doe',{'backend':'test.d6.ui','settings':{},'variables':inputs()['variables'],
            'candidates':[{'values':{'x':x}} for x in points]},len(points)))
        job,_=execute(app,wb,w);save(app,w)
        refs.append(wb.document_result_reference(w.document['id'],job))
    definition=dict(response='cost',unit='MPa',component='scalar',location='model',reduction='none')
    model=open_window(request('surrogate',{'result_refs':{'training':refs[0],'holdout':refs[1]},
        'response':definition,'points':[{'x':.4}]},1))
    mjob,prediction=execute(app,wb,model);save(app,model)
    original=deepcopy(prediction)
    original_id=model.document['id']
    model.candidates.selectRow(0);app.processEvents()
    assert model._selected_actual_candidate() is None
    model.next_method.setCurrentIndex(model.next_method.findData('confirm'))
    before=len(wb.manager.list())
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.StandardButton.Yes)
    model.next_method_button.click()
    wait(app,lambda:not model._busy and model.document['id']!=original_id,model)
    assert len(wb.manager.list())==before and model.document['runs']==[]
    assert model.edited_draft()['request']['inputs']['candidates'][0]['values']=={'x':.4}
    cjob,actual=execute(app,wb,model)
    assert actual['candidates'][0]['responses']['cost']['value']==pytest.approx(.16)
    save(app,model)
    reopened=open_window(identifier=model.document['id'])
    reopened.retry_result()
    wait(app,lambda:not reopened._busy and cjob in reopened._result_cache,reopened)
    reopened.candidates.selectRow(0);app.processEvents()
    from apps.research.numerical_methods import ConfirmationDialog
    dialogs=[]
    def read_dialog(dialog):
        table=dialog.findChild(QTableWidget)
        dialogs.append([table.item(i,1).text() for i in range(table.rowCount())])
        return QDialog.DialogCode.Rejected
    monkeypatch.setattr(ConfirmationDialog,'exec',read_dialog)
    jobs=len(wb.manager.list())
    reopened.confirmation_button.click()
    wait(app,lambda:not reopened._busy and bool(dialogs),reopened)
    assert dialogs[0][1]=='0.16'
    assert len(wb.manager.list())==jobs
    assert wb.document_result(original_id,mjob)==original
    first_actual=deepcopy(actual)
    # Unapplied edits must not relabel the selected OLD actual execution.
    reopened._edit_structure(lambda value:value['settings'].update(factor=2.))
    reopened.compare_prediction()
    wait(app,lambda:not reopened._busy and len(dialogs)==2,reopened)
    assert len(wb.manager.list())==jobs
    changed_job,changed_result=execute(app,wb,reopened)
    save(app,reopened)
    assert changed_result['candidates'][0]['responses']['cost']['value']==pytest.approx(.32)
    reopened.candidates.selectRow(0);app.processEvents()
    jobs=len(wb.manager.list())
    reopened.compare_prediction()
    wait(app,lambda:not reopened._busy and '평가 조건 변경' in reopened.message.text(),reopened)
    assert len(dialogs)==2 and len(wb.manager.list())==jobs
    assert wb.document_result(reopened.document['id'],cjob)==first_actual
    assert wb.document_result(original_id,mjob)==original



def test_canonical_combo_selection_survives_duplicate_labels_and_reopen(environment,monkeypatch):
    app,wb,open_window=environment
    from apps.research import numerical_methods
    # Physical objectives differ by reduction/location. Force a label collision
    # too: canonical itemData must remain authoritative even then.
    objectives=[dict(response='stress_xx',unit='MPa',component='xx',direction='minimize',
        reduction=reduction,location=location) for reduction,location in (('max','gage A'),('final','gage B'))]
    assert numerical_methods.objective_label(objectives[0])!=numerical_methods.objective_label(objectives[1])
    monkeypatch.setattr(numerical_methods,'objective_label',lambda row:'같은 표시명')
    value={'backend':'test.d6.ui','settings':{},'variables':inputs()['variables'],
        'objectives':objectives,'primary_index':0,'threshold_grid':[[10.]],'total_evaluation_budget':10}
    w=open_window(request('epsilon',value,10))
    index=w.method_sheet.model().index(0,1)
    delegate=w.method_sheet.itemDelegate()
    editor=delegate.createEditor(w.method_sheet,QStyleOptionViewItem(),index)
    delegate.setEditorData(editor,index)
    assert editor.currentData()==0
    editor.setCurrentIndex(1)
    delegate.setModelData(editor,w.method_sheet.model(),index)
    app.processEvents()
    assert w.edited_draft()['request']['inputs']['primary_index']==1
    assert w.edited_draft()['request']['inputs']['threshold_grid']==[[]]
    save(app,w)
    reopened=open_window(identifier=w.document['id'])
    index=reopened.method_sheet.model().index(0,1)
    editor=delegate.createEditor(reopened.method_sheet,QStyleOptionViewItem(),index)
    delegate.setEditorData(editor,index)
    assert editor.currentData()==1
    editor.setEditText('미지원 선택')
    delegate.setModelData(editor,reopened.method_sheet.model(),index)
    assert reopened.edited_draft()['request']['inputs']['primary_index']=='미지원 선택'
    assert wb.manager.list()==[]


def test_method_switch_restores_exact_model_with_its_edited_inputs(environment,monkeypatch):
    app,wb,open_window=environment
    models=[]
    for title,coefficient in (('모델 A',1000.),('모델 B',2000.)):
        draft=default_draft();draft['settings']['parameters']['E']=coefficient
        model=wb.document_open(kind='material',title=title,draft=draft)
        model=wb.document_command(model['id'],'document.save',{},session_id=model['session_id'],
            expected_generation=model['generation'])['document']
        models.append(model)
    selected=[models[0]['title']]
    monkeypatch.setattr(QInputDialog,'getItem',lambda parent,title,label,items,**kwargs:
        (next(item for item in items if selected[0] in item),True))
    monkeypatch.setattr(QMessageBox,'question',lambda *a,**k:QMessageBox.StandardButton.Yes)
    w=open_window(request('doe',{'backend':'','settings':{},'variables':[],'count':2},2))
    w.choose_model_document()
    wait(app,lambda:not w._busy and w.edited_draft().get('model_source',{}).get('document_id')==models[0]['id'],w)
    w.operation.setCurrentIndex(w.operation.findData('uq'))
    selected[0]=models[1]['title']
    w.choose_model_document()
    wait(app,lambda:not w._busy and w.edited_draft().get('model_source',{}).get('document_id')==models[1]['id'],w)
    save(app,w)
    reopened=open_window(identifier=w.document['id'])
    from apps.research import desktop
    opened=[]
    monkeypatch.setattr(desktop,'launch_tool',lambda client,tool,**kwargs:
        (opened.append(kwargs['document_id']) or {'status':'OPENED'}))
    for method,model in (('doe',models[0]),('uq',models[1]),('doe',models[0])):
        reopened.operation.setCurrentIndex(reopened.operation.findData(method))
        draft=reopened.edited_draft()
        assert draft['request']['inputs']['settings']==model['draft']['settings']
        assert draft['model_source']['document_id']==draft['source']['document_id']==model['id']
        reopened.open_model_source()
        wait(app,lambda:not reopened._busy and opened and opened[-1]==model['id'],reopened)
    save(app,reopened)
    again=open_window(identifier=reopened.document['id'])
    again.operation.setCurrentIndex(again.operation.findData('uq'))
    assert again.edited_draft()['model_source']['document_id']==models[1]['id']
    assert again.edited_draft()['request']['inputs']['settings']==models[1]['draft']['settings']
    assert wb.manager.list()==[]
