"""Mixed Plan source selection and admission; no solver or DOE execution."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QApplication,QInputDialog,QMessageBox,QTableWidget,QDialogButtonBox
from apps.research.request_plan_window import RequestPlanWindow
from examples.s1_windows_transfer import local_service,command
from examples.numerical_mixed_domains import model_settings,declarations
from caelab.numerical_document import request_draft
from caelab.evaluation_definition import document_reference
from test_numerical_evaluation_workflow import wait
from check_numerical_mixed_binding_windows import pin


@pytest.fixture
def app():return QApplication.instance() or QApplication([])


@pytest.mark.parametrize('accept',[False,True])
def test_saved_source_selection_is_explicit_and_preserves_typed_domains(app,tmp_path,monkeypatch,accept):
    with local_service(tmp_path) as (wb,client):
        source=client.document_open(kind='pde',title='공개 냉각 모델',draft={'backend':'pde.scipy.ode','settings':model_settings()})
        source=command(client,source,'document.save')['document']
        raw=declarations(('RK45','DOP853'))
        draft=request_draft({'purpose':'원본 선택 검사','operation':'doe',
            'inputs':{'variables':raw,'count':2,'responses':['temperature']},'budget':{'evaluations':2}})
        window=RequestPlanWindow(client,auto_open=False,poll_interval=0)
        def settled(predicate=lambda:True):wait(app,lambda:not window._busy and not window._callbacks and predicate())
        seen=[]
        def choose(parent,title,label,items,**kwargs):
            seen.append((title,label));return items[0],True
        monkeypatch.setattr(QInputDialog,'getItem',choose)
        monkeypatch.setattr(QMessageBox,'question',lambda *a:QMessageBox.StandardButton.Yes if accept else QMessageBox.StandardButton.Cancel)
        try:
            window.open_document(draft=draft);settled(lambda:window.document is not None)
            before=deepcopy(window.edited_draft())
            window.choose_model_document();settled()
            after=window.edited_draft()
            assert seen==[('저장 모델 선택','모델')]
            assert after['request']['inputs']['variables']==raw
            if accept:
                assert after['model_source']==document_reference(source)
                assert after['request']['inputs']['settings']==source['draft']['settings']
            else:assert after==before
            assert not wb.manager.list()
        finally:
            settled();window._allow_close=True;window.close();app.processEvents()


def test_typed_plan_budget_refusal_stays_saveable_without_dispatch(app,tmp_path):
    with local_service(tmp_path) as (wb,client):
        inputs=pin();inputs.update(backend='pde.scipy.ode',settings=model_settings())
        draft=request_draft({'purpose':'예산이 부족한 원 초안','operation':'doe',
            'inputs':inputs,'budget':{'evaluations':1}})
        window=RequestPlanWindow(client,auto_open=False,poll_interval=0)
        def settled(predicate=lambda:True):wait(app,lambda:not window._busy and not window._callbacks and predicate())
        try:
            window.open_document(draft=draft);settled(lambda:window.document is not None)
            assert window.document['diagnostics']
            assert not window.run_button.isEnabled()
            window.save_document();settled(lambda:bool(window.document.get('saved_revision')))
            assert window.document['draft']['request']['budget']=={'evaluations':1}
            assert window.document['draft']['request']['inputs']['candidates']==inputs['candidates']
            assert not wb.manager.list()
        finally:
            settled();window._allow_close=True;window.close();app.processEvents()


def test_retained_rank_deficiency_explains_design_recovery_without_changing_values(app):
    window=RequestPlanWindow(None,auto_open=False,poll_interval=0)
    result={'kind':'candidate_analysis','sensitivity':[{'metric':'temperature','unit':'K',
        'valid':False,'reason':'RANK_DEFICIENT','rank':2,'condition_number':None,
        'sample_ids':['C1','C2','C3'],'coefficients':[]}], 'exclusions':[{'id':'Cfailed'}]}
    original=deepcopy(result)
    window.selected_job=lambda:'Jcontrolled'
    window._result_cache['Jcontrolled']=result
    try:
        window._plot_selected_result()
        assert '독립적인 변수 조합' in window.result_summary.text()
        assert 'rank 2' in window.result_summary.text()
        assert '조건수 미제공' in window.result_summary.text()
        assert window.figure.axes[0].texts[0].get_text()=='설계행이 선형 종속이어서 회귀 영향도를 계산할 수 없습니다.'
        assert result==original
    finally:
        window._allow_close=True;window.close();app.processEvents()


def test_adoption_review_uses_original_input_metadata_and_full_path_fallback(app):
    window=RequestPlanWindow(None,auto_open=False,poll_interval=0)
    preview={'candidate_id':'Ccontrolled','target_document_id':'Qcontrolled','draft':{},'changes':[
        {'path':['settings','parameters',0,'value'],'input_id':'count','label':'공개 count','unit':'1','before':1,'after':2},
        {'path':['settings','parameters',1,'value'],'before':.1,'after':.2},
        {'path':['settings','solver','method'],'input_id':'solver-method','label':'시간 적분 방법','unit':'1','before':'RK45','after':'DOP853'}]}
    original=deepcopy(preview);seen=[]
    def review():
        dialog=app.activeModalWidget();table=dialog.findChild(QTableWidget,'candidateAdoptionChanges')
        seen.extend([[table.item(i,j).text() for j in range(table.columnCount())] for i in range(table.rowCount())])
        assert table.item(0,0).toolTip()=='count\nsettings/parameters/0/value'
        button=dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Cancel)
        assert button.text()=='취소';button.click()
    QTimer.singleShot(0,review)
    try:
        assert not window._review_pde_changes(preview)
        assert seen[0]==['공개 count','1','2','1','해당 없음']
        assert seen[1]==['settings/parameters/1/value','0.1','0.2','미제공','해당 없음']
        assert seen[2][0]=='시간 적분 방법' and preview==original
    finally:
        window._allow_close=True;window.close();app.processEvents()
