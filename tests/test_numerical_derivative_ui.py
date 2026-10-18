"""Controlled derivative display/preflight; no native solves or optimizer campaign."""
from copy import deepcopy
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication
from apps.research.s2_gradient_widgets import GradientEvidence
from experiment_expert.test_final_diagnosis import direct_problem,algebra,response
from caelab.experiment_final_diagnosis import evaluate_final


def test_one_sided_ordinary_fd_is_not_presented_as_adjoint():
    app=QApplication.instance() or QApplication([])
    problem=direct_problem(two=False,bound=True)
    result=evaluate_final(algebra,problem,budget_evaluations=4);original=deepcopy(result)
    assert result['execution_status']=='SUCCEEDED' and result['timing']['model_calls']==4
    window=GradientEvidence()
    try:
        window.set_result(result)
        assert 'ordinary-residual FD' in window.summary.text()
        assert window.gradients.rowCount()==0 and window.fd_stencils.rowCount()==1
        assert window.fd_stencils.item(0,1).text()=='한쪽 2차'
        assert window.fd_stencils.item(0,2).text()=='하한'
        h=float(window.fd_stencils.item(0,3).text());half=float(window.fd_stencils.item(0,4).text())
        assert half==pytest.approx(h/2)
        assert window.fd_stencils.item(0,7).text()=='경계 한쪽 범위'
        assert result==original
    finally:window.close();app.processEvents()


def test_insufficient_fd_budget_keeps_original_plan_and_missing_values():
    app=QApplication.instance() or QApplication([]);problem=direct_problem(two=False,bound=True)
    def forbidden(*args,**kwargs):raise AssertionError('Insufficient budget evaluated a model')
    result=evaluate_final(forbidden,problem,budget_evaluations=3);original=deepcopy(result)
    assert result['execution_status']=='REJECTED' and result['timing']['model_calls']==0
    window=GradientEvidence()
    try:
        window.set_result(result)
        assert '원 진단 실패' in window.summary.text() and '예산' in window.summary.text()
        assert '실제 평가 0회' in window.fd_summary.text() and '원 계획 4회' in window.fd_summary.text()
        assert window.fd_stencils.item(0,5).text()=='—' and window.fd_stencils.item(0,6).text()=='—'
        window.set_result({})
        assert window.fd_stencils.rowCount()==0 and '진단이 없습니다' in window.fd_summary.text()
        assert result==original
    finally:window.close();app.processEvents()


def test_de_result_uses_submitted_method_without_inventing_gradients():
    app=QApplication.instance() or QApplication([]);window=GradientEvidence()
    result={'kind':'optimization','execution_status':'PARTIAL_FAILURE','candidates':[
        {'execution_status':'FAILED','objective':None,'feasible':False,'failure_reason':'Maximum iterations reached'}]}
    original=deepcopy(result)
    try:
        window.set_result(result,submitted={'method':'differential_evolution'})
        assert '차분 진화(DE)' in window.summary.text() and window.gradients.rowCount()==0
        assert result==original
    finally:window.close();app.processEvents()


def test_nondifferentiable_failure_keeps_raw_fd_checks_and_original_limits():
    import math
    from caelab.numerical_candidate_detail import trial_detail
    app=QApplication.instance() or QApplication([]);problem=direct_problem(two=False)
    value=problem['candidate']['values']['x']
    def cusp(values,settings):return {'execution_status':'SUCCEEDED','responses':{'force':response([math.sqrt(abs(values['x']-value))]*4)}}
    problem['selected_trials'][0]=trial_detail(problem['experiments'][0],cusp(problem['candidate']['values'],{}),origin={'kind':'controlled'})
    problem['variables'][0].update(lower=value,value=value)
    result=evaluate_final(cusp,problem,budget_evaluations=4);original=deepcopy(result)
    assert result['execution_status']=='FAILED' and not result['experiment_analysis']['ordinary_jacobian']['step_halving']['stable']
    window=GradientEvidence()
    try:
        window.set_result(result)
        assert '원 진단 실패' in window.summary.text() and 'h/h2 일관성: 실패' in window.fd_summary.text()
        raw=result['experiment_analysis']['ordinary_jacobian']['step_halving']
        assert float(window.fd_stencils.item(0,5).text())==pytest.approx(raw['column_max_difference'][0],rel=1e-5)
        assert float(window.fd_stencils.item(0,6).text())==pytest.approx(raw['limits'][0],rel=1e-5)
        assert result==original
    finally:window.close();app.processEvents()


def test_method_combo_change_and_undo_preserve_original_adjoint_options():
    from PySide6.QtCore import Qt
    from PySide6.QtTest import QTest
    from PySide6.QtWidgets import QComboBox
    from apps.research.request_plan_window import RequestPlanWindow
    from caelab.numerical_document import request_draft
    from examples.s2_mdo_adjoint import declarations
    app=QApplication.instance() or QApplication([])
    _models,_definition,request=declarations('adjoint')
    document={'id':'Ncontrolled','kind':'numerical','session_id':'Scontrolled','title':'원 선형 계획',
        'generation':0,'input_revision':'Icontrolled','saved_revision':None,'runs':[],
        'draft':request_draft(request),'diagnostics':[],'dirty':False,'can_undo':False,'can_redo':False}
    window=RequestPlanWindow(None,auto_open=False,poll_interval=0);window._show_document(document);window.show()
    original=deepcopy(window.edited_draft())
    try:
        item=window.method_sheet.item(0,1);window.method_sheet.setCurrentItem(item);window.method_sheet.editItem(item);app.processEvents()
        editor=window.method_sheet.findChild(QComboBox);assert editor is not None
        editor.setCurrentIndex(editor.findData('differential_evolution'));QTest.keyClick(editor,Qt.Key.Key_Return);app.processEvents()
        assert window.edited_draft()['request']['inputs']['method']=='differential_evolution'
        assert 'verify_gradient' not in window.edited_draft()['request']['inputs'].get('options',{})
        assert window.undo_inputs() and window.edited_draft()==original
        assert window.edited_draft()['request']['inputs']['options']['verify_gradient'] is True
        assert window.document['draft']==document['draft'] and window.document['runs']==[]
    finally:window._allow_close=True;window.close();app.processEvents()


def test_shared_support_table_keeps_unassessed_and_unsupported_distinct():
    from apps.research.derivative_support_widgets import DerivativeSupport
    from caelab.linear_adjoint_contract import describe_methods
    app=QApplication.instance() or QApplication([]);widget=DerivativeSupport()
    payload={'derivative_methods':describe_methods(adjoint={'available':False,'reasons':['원 비선형 모델']})}
    original=deepcopy(payload)
    try:
        widget.set_descriptor(payload)
        assert widget.table.rowCount()==3
        assert widget.table.item(0,3).text()=='지원 안 됨' and '원 비선형 모델' in widget.table.item(0,4).text()
        assert widget.table.item(1,3).text()==widget.table.item(2,3).text()=='미확인'
        assert '현재 실행 환경은 확인하지 않았습니다.' in widget.summary.text()
        widget.set_descriptor(payload,message='선택 요청의 모델 범위를 확인했습니다.')
        assert '현재 실행 환경은 확인하지 않았습니다.' in widget.summary.text()
        assert payload==original
        widget.set_descriptor({});assert widget.table.rowCount()==0 and '미제공' in widget.summary.text()
    finally:widget.close();app.processEvents()


def test_late_support_ack_does_not_replace_a_changed_plan_context():
    import threading,time
    from apps.research.request_plan_window import RequestPlanWindow
    from caelab.numerical_document import request_draft
    from examples.s2_mdo_adjoint import declarations
    from caelab.linear_adjoint_contract import describe_methods
    app=QApplication.instance() or QApplication([])
    class Client:
        entered=threading.Event();release=threading.Event();calls=0
        def describe_inputs(self,request):
            self.calls+=1;self.entered.set();assert self.release.wait(5)
            return {'derivative_methods':describe_methods(),'derivative_admission':{'metadata_only':True}}
    client=Client();_models,_definition,request=declarations('adjoint')
    doc={'id':'Ncontrolled','kind':'numerical','session_id':'Scontrolled','title':'원 계획','generation':0,
        'input_revision':'Icontrolled','saved_revision':None,'runs':[],'draft':request_draft(request),
        'diagnostics':[],'dirty':False,'can_undo':False,'can_redo':False}
    window=RequestPlanWindow(client,auto_open=False,poll_interval=0);window._show_document(doc)
    try:
        window.check_adjoint_support();assert client.entered.wait(2)
        window.purpose.setText('지원 조회 후 편집');app.processEvents();client.release.set()
        end=time.monotonic()+5
        while (window._busy or window._callbacks) and time.monotonic()<end:app.processEvents();time.sleep(.005)
        assert not window._busy and not window._callbacks
        assert client.calls==2 and not getattr(window,'_derivative_support_windows',[])
        assert window.edited_draft()['request']['purpose']=='지원 조회 후 편집'
        assert window.document['draft']==doc['draft']
    finally:client.release.set();window._allow_close=True;window.close();app.processEvents()


@pytest.mark.parametrize('relative_step,reuse_result',[(.003,{'document_id':'Nretained','job_id':'Jretained'}),('1e',None)])
def test_fd_support_forwards_current_step_and_reuse_without_reinterpreting(monkeypatch,relative_step,reuse_result):
    import time
    from apps.research.request_plan_window import RequestPlanWindow
    from caelab.numerical_document import request_draft
    from caelab.linear_adjoint_contract import describe_methods
    import caelab.experiment_analysis_actions as actions
    app=QApplication.instance() or QApplication([]);calls=[]
    inputs={'evidence_reference':{'kind':'controlled_exact_reference'},'relative_step':relative_step}
    if reuse_result is not None:inputs['reuse_result']=deepcopy(reuse_result)
    def preview(client,*,evidence_reference,relative_step,reuse_result):
        calls.append(deepcopy((evidence_reference,relative_step,reuse_result)))
        return {'derivative_methods':describe_methods(diagnostic={'available':True,'reasons':[],'cost':0 if reuse_result else 5})}
    monkeypatch.setattr(actions,'read_analysis_source',preview)
    class Client:
        def describe_inputs(self,_request):raise AssertionError('Exact FD source must use its existing preview')
    draft=request_draft({'purpose':'현재 FD 요청','operation':'identification_final','inputs':inputs,'budget':{'evaluations':1}})
    doc={'id':'Ncontrolled','kind':'numerical','session_id':'Scontrolled','title':'원 계획','generation':0,
        'input_revision':'Icontrolled','saved_revision':None,'runs':[],'draft':draft,
        'diagnostics':[],'dirty':False,'can_undo':False,'can_redo':False}
    window=RequestPlanWindow(Client(),auto_open=False,poll_interval=0);window._show_document(doc)
    try:
        before=deepcopy(window.edited_draft());window.check_adjoint_support()
        end=time.monotonic()+5
        while (window._busy or window._callbacks) and time.monotonic()<end:app.processEvents();time.sleep(.005)
        assert not window._busy and not window._callbacks
        assert calls==[(inputs['evidence_reference'],relative_step,reuse_result)]
        assert window.edited_draft()==before and window.document['draft']==doc['draft']
        dialog=window._derivative_support_windows[-1]
        assert '현재 실행 환경은 확인하지 않았습니다.' in dialog.content.summary.text()
        dialog.close();app.processEvents()
    finally:window._allow_close=True;window.close();app.processEvents()
