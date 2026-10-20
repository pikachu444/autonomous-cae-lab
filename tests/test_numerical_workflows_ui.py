"""Focused real Qt + real owners; algebra is an explicit test-only evaluator."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
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


def test_short_worksheets_leave_space_and_long_inputs_remain_scrollable(environment):
    from apps.research.numerical_window import size_table_to_rows
    app,wb,open_window=environment
    value=inputs();value['variables']*=2
    value['variables'][1]=dict(value['variables'][1],id='긴 사용자 계수 이름',unit='MPa')
    w=open_window(request('uq',value))
    w.resize(1100,780);app.processEvents()
    assert w.variable_sheet.rowCount()==2
    assert w.variable_sheet.maximumHeight()<180
    assert w.response_sheet.maximumHeight()<220
    assert w.method_sheet.maximumHeight()<280
    original=deepcopy(w.edited_draft())
    w.variable_sheet.item(0,2).setText('1e')
    assert w.edited_draft()['request']['inputs']['variables'][0]['value']=='1e'
    w._refresh_worksheet()
    assert w.variable_sheet.item(0,2).text()=='1e'
    table=QTableWidget(30,2)
    height=size_table_to_rows(table)
    assert height==sum(table.rowHeight(i) for i in range(6))+max(table.horizontalHeader().height(),table.horizontalHeader().sizeHint().height())+2*table.frameWidth()+table.horizontalScrollBar().sizeHint().height()
    assert table.rowCount()==30 and height<400
    assert original['request']['inputs']['variables'][1]['unit']=='MPa'
    assert wb.manager.list()==[]


def test_candidate_plot_labels_keep_exact_units_mask_and_user_axis():
    """Presentation-only fixture; no solver/evaluator result is manufactured."""
    from matplotlib.figure import Figure
    from apps.research.numerical_window import axis_label
    selected={'candidate_id':'opaque-test-candidate','execution_status':'SUCCEEDED',
        'responses':{'측정 응력':{'kind':'series','unit':'MPa','value':[2.,7.,4.],
            'axes':[{'name':'사용자 변형 축','unit':'1','values':[0.,.1,.2]}],'mask':[True,False,True]}}}
    result={'candidates':[selected]};before=deepcopy(result)
    view=SimpleNamespace(figure=Figure(),_selected_actual_candidate=lambda:selected)
    RequestPlanWindow._plot_candidate_response(view,result,'측정 응력')
    axis=view.figure.axes[0]
    assert axis.get_title()=='후보 1 / 측정 응력'
    assert axis.get_xlabel()=='사용자 변형 축 [1]'
    assert axis.get_ylabel()=='측정 응력 [MPa]'
    assert list(axis.lines[0].get_xdata())==[0.,.1,.2]
    import math
    assert math.isnan(axis.lines[0].get_ydata()[1])
    assert result==before
    assert axis_label({'name':'time','unit':'s'})=='시간 [s]'


@pytest.mark.parametrize('repeat_component',[False,True])
def test_pareto_projection_labels_and_candidate_selection_do_not_change_result(monkeypatch,repeat_component):
    from caelab.storage import canonical_hash
    app=QApplication.instance() or QApplication([])
    definitions=[dict(response=name,unit='N',component=name if repeat_component else 'scalar',location='model',reduction='none',direction=direction)
        for name,direction in (('사용자 힘 A','minimize'),('사용자 힘 B','maximize'))]
    draft=request('epsilon',dict(objectives=definitions))
    result={'kind':'epsilon_optimization','variables':[dict(id='x',unit='mm')],
        'pareto':{'nondominated_ids':['Cfixture2']},'children':[],
        'candidates':[dict(candidate_id='Cfixture'+str(i),execution_status='SUCCEEDED',values={'x':i},
            responses={name:dict(kind='scalar',unit='N',component=name if repeat_component else 'scalar',location='model',value=value)
                for name,value in (('사용자 힘 A',float(i)),('사용자 힘 B',float(10-i)))}) for i in (1,2)]}
    original=deepcopy(result);w=RequestPlanWindow(None,auto_open=False,poll_interval=0)
    w.document=dict(id='Nfixture',session_id='Sfixture',draft=draft,runs=[dict(job_id='Jfixture',draft=draft)])
    monkeypatch.setattr(w,'selected_job',lambda:'Jfixture');monkeypatch.setattr(w,'_update_actions',lambda:None)
    w._result_cache['Jfixture']=result
    try:
        w._draw_result();w.candidates.selectRow(1);app.processEvents()
        axis=w.figure.axes[0]
        assert axis.get_xlabel()=='사용자 힘 A [N] 최소화' and axis.get_ylabel()=='사용자 힘 B [N] 최대화'
        assert axis.get_title()=='다목적 후보 / 선택 후보 2'
        assert '사용자 힘 A 사용자 힘 A' not in w.pareto_x.itemText(0)
        assert w._selected_actual_candidate()['candidate_id']=='Cfixture2'
        assert canonical_hash(result)==canonical_hash(original)
        assert w.candidates.item(1,2).data(Qt.ItemDataRole.UserRole)==2
        def plotted_points():
            return {identifier:tuple(point) for artist in w.figure.axes[0].collections
                if hasattr(artist,'_candidate_ids')
                for identifier,point in zip(artist._candidate_ids,artist.get_offsets())}
        assert plotted_points()=={'Cfixture1':(1.,9.),'Cfixture2':(2.,8.)}
        w.pareto_x.setCurrentIndex(w.pareto_x.findData(1))
        w.pareto_y.setCurrentIndex(w.pareto_y.findData(0))
        app.processEvents()
        axis=w.figure.axes[0]
        assert axis.get_xlabel()=='사용자 힘 B [N] 최대화' and axis.get_ylabel()=='사용자 힘 A [N] 최소화'
        assert plotted_points()=={'Cfixture1':(9.,1.),'Cfixture2':(8.,2.)}
        assert w._selected_actual_candidate()['candidate_id']=='Cfixture2'
        assert result==original
        from matplotlib.layout_engine import TightLayoutEngine
        for width,height in ((1440,900),(1100,780)):
            w.resize(width,height);w.show();w.work_pages.setCurrentWidget(w.results_panel);app.processEvents()
            w._plot_selected_result();w.canvas.draw()
            assert isinstance(w.figure.get_layout_engine(),TightLayoutEngine)
            renderer=w.canvas.get_renderer()
            axis=w.figure.axes[0]
            for label in (axis.title,axis.xaxis.label,axis.yaxis.label):
                bounds=label.get_window_extent(renderer)
                assert bounds.x0>=0 and bounds.y0>=0
                assert bounds.x1<=w.canvas.width()+1 and bounds.y1<=w.canvas.height()+1
            assert canonical_hash(result)==canonical_hash(original)
    finally:w._allow_close=True;w.close();app.processEvents()


@pytest.fixture
def recovery_environment(tmp_path):
    """The existing HTTP recovery owner, without installing an evaluator."""
    import threading
    from apps.lab.service import LabService
    from apps.lab.server import LabHTTPServer
    from caelab.workbench_client import Client as HttpClient
    app=QApplication.instance() or QApplication([])
    service=LabService(tmp_path);server=LabHTTPServer(service,0)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
    client=HttpClient(f'http://127.0.0.1:{server.server_port}')
    windows=[]
    def open_view(kind,identifier=None):
        from apps.research.numerical_window import NumericalWindow
        from caelab.numerical_document import from_material_document
        if identifier is None:
            if kind=='request':
                draft=request('doe',{'variables':[dict(id='x',value=.5,lower=0.,upper=1.,unit='1')],
                    'responses':['cost'],'count':4,'seed':2,'method':'lhs'},8)
            else:
                material=client.document_open(kind='material',draft=default_draft())
                draft=from_material_document(material)
            document=client.document_open(kind='numerical',draft=draft)
            document=client.document_command(document['id'],'document.save',{},
                session_id=document['session_id'],expected_generation=document['generation'])['document']
        else:document=client.document_read(identifier)
        view=(RequestPlanWindow if kind=='request' else NumericalWindow)(client,auto_open=False,poll_interval=0)
        windows.append(view);view._show_document(document);view.show()
        wait(app,lambda:not view._busy and not view._callbacks,view)
        return view,document
    try:yield app,server.workbench,client,open_view
    finally:
        for view in windows:view._allow_close=True;view.close()
        assert QThreadPool.globalInstance().waitForDone(5000)
        server.shutdown();server.server_close();thread.join(2);service.shutdown()
        for view in windows:view.deleteLater()
        app.processEvents()


def _recovery_later(kind,callback):
    from PySide6.QtCore import QTimer
    def find():
        dialog=next((view for view in QApplication.topLevelWidgets() if isinstance(view,kind) and view.isVisible()),None)
        if dialog is None:QTimer.singleShot(5,find)
        else:callback(dialog)
    QTimer.singleShot(5,find)


def _recovery_question(caption):
    _recovery_later(QMessageBox,lambda dialog:next(button for button in dialog.buttons() if button.text()==caption).click())


def _unfinished_numerical(app,view):
    from PySide6.QtWidgets import QLineEdit
    table=view.variable_sheet if isinstance(view,RequestPlanWindow) else view.variables
    cell=table.item(0,2);table.setCurrentItem(cell);table.editItem(cell);app.processEvents()
    line=next(editor for editor in table.findChildren(QLineEdit) if editor.isVisible())
    line.setText('1e');line.setSelection(2,-2)
    return table,line


@pytest.mark.parametrize('kind',['request','material_plan'])
def test_raw_recovery_cancel_keep_and_exact_delegate_without_apply(recovery_environment,kind):
    from PySide6.QtCore import QTimer
    from PySide6.QtWidgets import QLineEdit
    from apps.research.data_material_recovery_dialog import RecoveryKeepDialog
    from apps.research.data_material_recovery_read import RecoveryReadDialog
    from apps.research.data_material_recovery_host import inspect_recovery
    from apps.research.numerical_recovery import numerical_raw_snapshot
    app,wb,client,open_view=recovery_environment
    view,document=open_view(kind);table,line=_unfinished_numerical(app,view)
    original=deepcopy(document);jobs=wb.manager.list()
    _recovery_question('취소');view.close();app.processEvents()
    assert view.isVisible() and line.text()=='1e' and line.selectedText()=='1e' and line.cursorPosition()==0
    assert numerical_raw_snapshot(view)['local_draft']==document['draft']
    def keep(dialog):
        def ready():
            if dialog.keep_button.isEnabled():dialog.keep()
            else:QTimer.singleShot(5,ready)
        ready()
    _recovery_question('편집 원문 보관');_recovery_later(RecoveryKeepDialog,keep);view.close()
    wait(app,lambda:not view.isVisible(),view)
    raw=client.data_material('recovery.read',{'document_id':document['id']})['capsules'][-1]['capsule']['raw']
    assert any(cell['raw_text']=='1e' and cell['editor_kind']=='unfinished' for cell in raw['cells'])
    fresh,_=open_view(kind,document['id'])
    def resume(dialog):
        def ready():
            if dialog.resume_button.isEnabled():dialog.resume()
            else:QTimer.singleShot(5,ready)
        ready()
    _recovery_later(RecoveryReadDialog,resume);inspect_recovery(fresh)
    wait(app,lambda:getattr(fresh,'_recovery_review',None) is None,fresh)
    restored_table=fresh.variable_sheet if kind=='request' else fresh.variables
    restored=next(editor for editor in restored_table.findChildren(QLineEdit) if editor.isVisible())
    assert (restored.text(),restored.selectedText(),restored.cursorPosition())==('1e','1e',0)
    after=client.document_read(document['id'])
    for key in ('draft','generation','input_revision','saved_revision','runs'):assert after[key]==original[key]
    assert wb.manager.list()==jobs


@pytest.mark.parametrize('failure',['capsule','base'])
def test_raw_recovery_write_failure_and_base_change_keep_exact_plan(recovery_environment,monkeypatch,failure):
    from pathlib import Path
    from PySide6.QtCore import QTimer
    from apps.research.data_material_recovery_dialog import RecoveryKeepDialog
    import caelab.related_save_recovery as recovery
    app,wb,client,open_view=recovery_environment
    view,document=open_view('request');_,line=_unfinished_numerical(app,view)
    if failure=='base':
        draft=deepcopy(document['draft']);draft['request']['purpose']='다른 창의 편집'
        client.document_command(document['id'],'numerical.update',{'draft':draft},
            session_id=document['session_id'],expected_generation=document['generation'])
    else:
        original=recovery.save_json
        def fail(path,value):
            if Path(path).parent.name=='raw-recovery':raise OSError('bounded capsule write failure')
            return original(path,value)
        monkeypatch.setattr(recovery,'save_json',fail)
        def keep(dialog):
            def ready():
                if dialog.outcome is not None:
                    assert not dialog.outcome['all_kept'];dialog.reject()
                elif dialog.keep_button.isEnabled():dialog.keep();QTimer.singleShot(5,ready)
                else:QTimer.singleShot(5,ready)
            ready()
        _recovery_later(RecoveryKeepDialog,keep)
    _recovery_question('편집 원문 보관');view.close()
    wait(app,lambda:getattr(view,'_recovery_review',None) is None,view)
    assert view.isVisible() and (line.text(),line.selectedText(),line.cursorPosition())==('1e','1e',0)
    assert not client.data_material('recovery.read',{'document_id':document['id']})['capsules']
    assert client.document_read(document['id'])['draft']==(draft if failure=='base' else document['draft'])
    assert not wb.manager.list()


def test_raw_recovery_paste_advanced_leaf_selection_and_local_undo(recovery_environment):
    from PySide6.QtWidgets import QLineEdit
    from apps.research.request_plan_window import DATA
    from apps.research.numerical_recovery import numerical_raw_snapshot, restore_numerical_raw
    app,wb,client,open_view=recovery_environment
    view,document=open_view('request')
    table=view.variable_sheet;table.setCurrentItem(table.item(0,2))
    text='1e\t잘못된 하한';app.clipboard().setText(text);assert table.paste_cells()
    app.processEvents()
    view.work_pages.setCurrentIndex(0)
    view.input_tabs.setCurrentWidget(view.advanced_scroll)
    app.processEvents()
    tree=view.inputs
    item=next(tree.topLevelItem(0).child(row) for row in range(tree.topLevelItem(0).childCount())
              if tree.topLevelItem(0).child(row).data(0,DATA)['path']==('count',))
    tree.setCurrentItem(item,1);tree.editItem(item,1);app.processEvents()
    line=next(editor for editor in tree.findChildren(QLineEdit) if editor.isVisible())
    line.setText('3e');line.setSelection(2,-1)
    raw=numerical_raw_snapshot(view)
    assert raw['paste']['variable_sheet']['raw_text']==text
    assert raw['focus']['selection']==[1,1] and raw['focus']['cursor']==1
    fresh,_=open_view('request',document['id']);restore_numerical_raw(fresh,raw)
    restored=next(editor for editor in fresh.inputs.findChildren(QLineEdit) if editor.isVisible())
    assert (restored.text(),restored.selectedText(),restored.cursorPosition())==('3e','e',1)
    assert fresh.input_tabs.currentWidget() is fresh.advanced_scroll
    assert fresh.variable_sheet.item(0,2).text()=='1e'
    assert fresh.variable_sheet.item(0,3).text()=='잘못된 하한'
    assert fresh.variable_sheet.raw_paste['raw_text']==text
    assert sorted([[i.row(),i.column()] for i in fresh.variable_sheet.selectedIndexes()])==sorted(raw['selection']['variable_sheet'])
    fresh.undo_inputs()
    assert fresh.edited_draft(commit=False)==document['draft']
    after=client.document_read(document['id'])
    for key in ('draft','generation','input_revision','saved_revision','runs'):assert after[key]==document[key]
    assert not wb.manager.list()


def test_raw_recovery_explicit_save_commits_and_saves_without_running(recovery_environment):
    app,wb,client,open_view=recovery_environment
    view,document=open_view('request');_,line=_unfinished_numerical(app,view)
    line.setText('2.5')
    _recovery_question('저장');view.close()
    wait(app,lambda:not view.isVisible(),view)
    saved=client.document_read(document['id'])
    assert saved['draft']['request']['inputs']['variables'][0]['value']==2.5
    assert saved['saved_revision']!=document['saved_revision'] and not saved['dirty']
    assert not client.data_material('recovery.read',{'document_id':document['id']})['capsules']
    assert not wb.manager.list()


@pytest.mark.parametrize('failed_open',[False,True])
@pytest.mark.parametrize('action',['close','new'])
def test_raw_recovery_empty_window_can_close_and_open_after_failed_load(recovery_environment,failed_open,action):
    from apps.research.numerical_window import NumericalWindow
    app,wb,client,_=recovery_environment
    view=NumericalWindow(client,auto_open=False,poll_interval=0)
    view.show()
    try:
        if failed_open:
            view.open_document(document_id='N'+'0'*32)
            wait(app,lambda:not view._busy and not view._callbacks,view)
        assert view.document is None
        called=[]
        view._busy=True;view._leave(lambda:called.append('busy'))
        assert not called
        view._busy=False
        view._leave(lambda:called.append('empty'))
        assert called==['empty']
        if action=='close':
            view.close();wait(app,lambda:not view.isVisible(),view)
            assert view._closed and not wb.manager.list()
            return
        view._leave(lambda:view.open_document())
        wait(app,lambda:view.document is not None and not view._busy and not view._callbacks,view)
        # A real document's unresolved variable command still blocks departure.
        view.variable_editor._history_command={'operation':'document.undo'}
        view._leave(lambda:called.append('pending'))
        assert called==['empty']
        view.variable_editor._history_command=None
        assert not wb.manager.list()
    finally:
        view._allow_close=True;view.close()


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
    from PySide6.QtCore import QItemSelectionModel
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
        assert w._selected_actual_candidate()['candidate_id']==identifier
    w._edit_structure(lambda current:current['thresholds'][0].update(unit='Pa'))
    draft=deepcopy(w.edited_draft())
    assert w._selected_actual_candidate()['candidate_id']==identifier
    # Keyboard focus and the highlighted result can refer to different rows.
    selected_row=w.candidates.selectionModel().selectedRows()[0].row()
    other_row=(selected_row+1)%w.candidates.rowCount()
    w.candidates.selectionModel().setCurrentIndex(w.candidates.model().index(other_row,0),
        QItemSelectionModel.SelectionFlag.NoUpdate)
    assert w._selected_actual_candidate()['candidate_id']==identifier
    selected_item=w.candidates.item(selected_row,0)
    w._draw_result()  # A result callback only redraws the frozen run.
    assert w.edited_draft()==draft and w.work_pages.currentWidget() is w.results_panel
    assert w._selected_actual_candidate()['candidate_id']==identifier
    assert w.candidates.item(selected_row,0) is selected_item
    assert '[MPa]' in w.figure.axes[0].get_xlabel()
    assert result['probability_statistics'][0]['threshold']['unit']=='MPa'
    w._result_cache.pop(job)
    w._draw_result()
    assert not w.result_summary.text()


def test_queued_result_retry_keeps_highlight_until_fresh_read(environment,monkeypatch):
    import threading
    app,wb,open_window=environment
    install_algebra(monkeypatch)
    w=open_window(request('uq',inputs()))
    job,result=execute(app,wb,w)
    wait(app,lambda:not w._busy and not w._callbacks and w._queued_result_retry is None,w)
    w.work_pages.setCurrentWidget(w.results_panel)
    w.candidates.selectRow(3)
    selected=w._selected_actual_candidate()['candidate_id']
    selected_item=w.candidates.item(3,0)
    reading,release=threading.Event(),threading.Event()
    original=w.client.document_read
    def read(identifier):
        reading.set()
        assert release.wait(5)
        return original(identifier)
    monkeypatch.setattr(w.client,'document_read',read)
    try:
        w.refresh_document();wait(app,reading.is_set,w)
        w.retry_result()
        assert w._queued_result_retry==(w.document['id'],job)
        assert w._selected_actual_candidate()['candidate_id']==selected
        release.set()
        wait(app,lambda:w._queued_result_retry is None and not w._busy and not w._callbacks,w)
        assert w._selected_actual_candidate()['candidate_id']==selected
        assert w.candidates.item(3,0) is selected_item
        assert w._result_cache[job]==result
        changed=deepcopy(result)
        changed['diagnostics']={'reader_note':'New retained diagnostic'}
        monkeypatch.setattr(w.client,'document_result',lambda *args,**kwargs:deepcopy(changed))
        w.retry_result()
        wait(app,lambda:w._queued_result_retry is None and not w._busy and not w._callbacks,w)
        assert w._result_cache[job]==changed
        assert w._selected_actual_candidate() is None
    finally:
        release.set()


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
    saved_opened=[]
    monkeypatch.setattr(desktop,'open_saved_reference',lambda client,reference:
        (saved_opened.append(deepcopy(reference)) or {'status':'OPENED'}))
    monkeypatch.setattr(desktop,'launch_tool',lambda client,tool,**kwargs:
        (opened.append((tool,kwargs['document_id'])) or {'status':'OPENED'}))
    w.open_model_source();wait(app,lambda:not w._busy and len(saved_opened)==1,w)
    assert saved_opened==[w.edited_draft()['model_source']]
    w.open_source();wait(app,lambda:not w._busy and len(opened)==1,w)
    assert opened==[('material',model['id'])]
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
    original_result=deepcopy(result)
    previews=[]
    monkeypatch.setattr(w,'_review_pde_changes',lambda preview:(previews.append(deepcopy(preview)) or False))
    w.work_pages.setCurrentWidget(w.results_panel)
    wait(app,lambda:not w._busy and not w._callbacks and not getattr(w,'_retained_labels_scheduled',False)
         and w.candidates.rowCount()==2,w)
    w.candidates.selectRow(0);app.processEvents()
    wait(app,w.pde_adopt_button.isEnabled,w)
    assert w._selected_actual_candidate()['candidate_id']==result['candidates'][0]['candidate_id']
    w.pde_adopt_button.click()
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
    wait(app,lambda:not reopened._callbacks and not getattr(reopened,'_retained_labels_scheduled',False),reopened)
    reopened.candidates.selectRow(0);app.processEvents()
    monkeypatch.setattr(reopened,'_review_pde_changes',lambda preview:True)
    jobs=len(wb.manager.list())
    wait(app,reopened.pde_adopt_button.isEnabled,reopened)
    assert reopened._selected_actual_candidate()['candidate_id']==result['candidates'][0]['candidate_id']
    reopened.pde_adopt_button.click()
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
    assert wb.document_result(reopened.document['id'],job)==original_result


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
        return (items[0],title!='모델 조건 선택')
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
    monkeypatch.setattr(desktop,'open_saved_reference',lambda client,reference:
        (opened.append(deepcopy(reference)) or {'status':'OPENED'}))
    for method,model in (('doe',models[0]),('uq',models[1]),('doe',models[0])):
        reopened.operation.setCurrentIndex(reopened.operation.findData(method))
        draft=reopened.edited_draft()
        assert draft['request']['inputs']['settings']==model['draft']['settings']
        assert draft['model_source']['document_id']==draft['source']['document_id']==model['id']
        reopened.open_model_source()
        wait(app,lambda:not reopened._busy and opened and opened[-1]==draft['model_source'],reopened)
    save(app,reopened)
    again=open_window(identifier=reopened.document['id'])
    again.operation.setCurrentIndex(again.operation.findData('uq'))
    assert again.edited_draft()['model_source']['document_id']==models[1]['id']
    assert again.edited_draft()['request']['inputs']['settings']==models[1]['draft']['settings']
    assert wb.manager.list()==[]


def test_saved_model_open_keeps_old_input_after_owner_edit(environment,monkeypatch):
    app,wb,open_window=environment
    from caelab.evaluation_definition import document_reference
    from apps.research import desktop
    model=wb.document_open(kind='material',title='변경 전 재료 입력',draft=default_draft())
    def command(document,operation,arguments=None):
        return wb.document_command(document['id'],operation,arguments or {},session_id=document['session_id'],
            expected_generation=document['generation'])['document']
    model=command(model,'document.save');old_reference=document_reference(model)
    draft=request('doe',{'backend':model['draft']['backend'],'settings':deepcopy(model['draft']['settings']),
        'variables':[],'count':2},2)
    draft['source']=draft['model_source']=deepcopy(old_reference)
    w=open_window(draft)
    changed=deepcopy(model['draft']);changed['settings']['parameters']['E']=2000.
    model=command(model,'material.update',{'draft':changed});model=command(model,'document.save')
    assert document_reference(model)!=old_reference
    reads=[]
    def saved(client,reference):
        resolved=client.research_reference({**reference,'kind':'document','document_kind':reference['kind']})
        reads.append((deepcopy(reference),resolved));return {'status':'OPENED'}
    monkeypatch.setattr(desktop,'open_saved_reference',saved)
    monkeypatch.setattr(desktop,'launch_tool',lambda *a,**kw:pytest.fail('Saved input must not open the mutable owner'))
    w.model_open_button.click();wait(app,lambda:not w._busy and bool(reads),w)
    assert reads[0][0]==old_reference
    assert reads[0][1]['document']['draft']['settings']['parameters']['E']==1000.
    assert wb.document_read(model['id'])['draft']['settings']['parameters']['E']==2000.
    assert wb.manager.list()==[]


@pytest.mark.skipif(not os.environ.get('CAE_NUMERICAL_UX_STORE'),reason='requires retained input and exclusive desktop lease')
def test_actual_saved_numerical_workspace_ui(tmp_path,monkeypatch):
    """Supplied actual retained candidates, existing HTTP read/edit/save only."""
    import hashlib,json,shutil,threading
    from pathlib import Path
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QLineEdit
    from apps.lab.service import LabService
    from apps.lab.server import LabHTTPServer
    from caelab.workbench_client import Client as HttpClient
    from caelab.storage import canonical_hash
    source=Path(os.environ['CAE_NUMERICAL_UX_STORE']).resolve()
    output=Path(os.environ['CAE_NUMERICAL_UX_OUTPUT']).resolve();output.mkdir(parents=True,exist_ok=False)
    store=output/'store';shutil.copytree(source,store)
    def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()
    originals={str(path.relative_to(source)):digest(path) for path in source.rglob('*') if path.is_file()}
    paths=['apps/research/numerical_window.py','apps/research/request_plan_window.py','tests/test_numerical_workflows_ui.py']
    pins={name:digest(Path(name)) for name in paths}
    (output/'source-launch.json').write_text(json.dumps(pins,indent=2),encoding='utf-8')
    def wait(app,ready,window=None):
        deadline=time.monotonic()+30
        while time.monotonic()<deadline:
            app.processEvents()
            if ready():return
            time.sleep(.005)
        raise AssertionError(window.message.text() if window else 'retained HTTP/Qt read did not settle within 30 seconds')
    app=QApplication.instance() or QApplication([])
    from apps.research.appearance import apply_appearance
    apply_appearance(app)
    service=LabService(store);server=LabHTTPServer(service,0)
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01},daemon=True);thread.start()
    client=HttpClient(f'http://127.0.0.1:{server.server_port}');windows=[]
    def forbidden(*args,**kwargs):raise AssertionError('saved UI must not execute')
    monkeypatch.setattr(server.workbench,'submit',forbidden);monkeypatch.setattr(server.workbench.manager,'submit',forbidden)
    def capture(window,name):
        window.raise_();window.activateWindow();app.processEvents();QTest.qWait(80)
        assert window.grab().save(str(output/(name+'.png')))
    try:
        identifier=os.environ.get('CAE_NUMERICAL_UX_DOCUMENT')
        documents=client.documents()['documents']
        documents=[client.document_read(row['id']) for row in documents if row['kind']=='numerical']
        document=client.document_read(identifier) if identifier else next(row for row in documents
            if row.get('runs') and row['draft'].get('mode')=='request')
        jobs=deepcopy(server.workbench.manager.list());job=document['runs'][-1]['job_id']
        result=client.document_result(document['id'],job);result_hash=canonical_hash(result)
        w=RequestPlanWindow(client,document_id=document['id'],poll_interval=0);windows.append(w);w.show()
        wait(app,lambda:w.document is not None and not w._busy and not w._callbacks
            and not getattr(w,'_retained_labels_scheduled',False),w)
        w._populate_runs(job);w.refresh_result()
        wait(app,lambda:job in w._result_cache and not w._busy and not w._callbacks,w)
        for size,label in (((1440,900),'normal'),((1100,780),'narrow')):
            w.resize(*size);w.work_pages.setCurrentWidget(w.plan_page);app.processEvents()
            assert w.variable_sheet.height()<400
            capture(w,'numerical-plan-'+label)
            w.work_pages.setCurrentWidget(w.results_panel);w.candidates.selectRow(0)
            names=sorted(w._candidate_plot_names)
            if result.get('kind')=='epsilon_optimization':
                w.plot_response.setCurrentIndex(0)
                w.pareto_x.setCurrentIndex(min(2,w.pareto_x.count()-1));w.pareto_y.setCurrentIndex(min(1,w.pareto_y.count()-1))
            elif names:w.plot_response.setCurrentIndex(w.plot_response.findData({'candidate_response':names[0]}))
            capture(w,'numerical-results-'+label)
        selected=w._selected_actual_candidate();assert selected is not None
        assert selected==result['candidates'][0]
        w._draw_result();app.processEvents()
        assert w._selected_actual_candidate()['candidate_id']==selected['candidate_id']
        if os.environ.get('CAE_NUMERICAL_UX_READ_ONLY')=='1':
            assert canonical_hash(client.document_result(document['id'],job))==result_hash
            assert server.workbench.manager.list()==jobs
            assert originals=={str(path.relative_to(source)):digest(path) for path in source.rglob('*') if path.is_file()}
            assert pins=={name:digest(Path(name)) for name in paths}
            (output/'result.json').write_text(json.dumps(dict(platform=app.platformName(),source=str(source),
                document_id=document['id'],job_id=job,result_sha256=result_hash,source_pins=pins,
                candidate_id=selected['candidate_id'],read_only=True,new_jobs=0),ensure_ascii=False,indent=2),encoding='utf-8')
            return
        w.work_pages.setCurrentWidget(w.plan_page)
        cell=w.variable_sheet.item(0,2);old=cell.text()
        w.variable_sheet.setCurrentItem(cell);w.variable_sheet.editItem(cell);app.processEvents()
        editor=QApplication.focusWidget();assert isinstance(editor,QLineEdit)
        editor.setText('1e');capture(w,'numerical-unfinished-narrow')
        QTest.keyClick(editor,Qt.Key.Key_Escape);app.processEvents();assert cell.text()==old
        before=deepcopy(w.edited_draft());w.purpose.setText(w.purpose.text()+' 확인')
        w.apply_inputs();wait(app,lambda:not w._busy and not w.local_dirty,w)
        assert w.document['draft']['request']['inputs']==before['request']['inputs']
        w.save_document();wait(app,lambda:not w._busy and not w.document['dirty'],w)
        saved=deepcopy(w.document);w._allow_close=True;w.close();app.processEvents()
        reopened=RequestPlanWindow(client,document_id=document['id'],poll_interval=0);windows.append(reopened);reopened.show()
        wait(app,lambda:reopened.document is not None and not reopened._busy and not reopened._callbacks,reopened)
        assert reopened.document['draft']==saved['draft'] and reopened.document['saved_revision']==saved['saved_revision']
        reopened.resize(1100,780);capture(reopened,'numerical-reopened-narrow')
        assert canonical_hash(client.document_result(document['id'],job))==result_hash
        assert server.workbench.manager.list()==jobs
        assert originals=={str(path.relative_to(source)):digest(path) for path in source.rglob('*') if path.is_file()}
        assert pins=={name:digest(Path(name)) for name in paths}
        record=dict(platform=app.platformName(),source=str(source),document_id=document['id'],job_id=job,
            result_sha256=result_hash,source_pins=pins,candidate_id=selected['candidate_id'],raw_cancel=True,
            apply_save_reopen=True,jobs_before=len(jobs),jobs_after=len(jobs),new_jobs=0,
            scope='Qt events; no physical OS input or engineering qualification')
        (output/'result.json').write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding='utf-8')
    finally:
        for window in reversed(windows):window._allow_close=True;window.close()
        assert QThreadPool.globalInstance().waitForDone(5000)
        app.processEvents();server.shutdown();server.server_close();thread.join(3);service.shutdown()
