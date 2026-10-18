"""Controlled retained UI records; no fit, solver, or physical validation."""
from copy import deepcopy
import math
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import Qt,QCoreApplication,QEvent
from PySide6.QtWidgets import QApplication,QTreeWidgetItem
from apps.research.numerical_candidate_detail_window import NumericalCandidateDetailWindow
from apps.research.numerical_window import NumericalWindow
from apps.research.request_plan_window import RequestPlanWindow
from caelab.numerical_candidate_detail import experiment_snapshot,trial_detail


@pytest.mark.parametrize('role',['fit','holdout'])
def test_same_retained_mask_weight_table_and_curve(role,monkeypatch):
    app=QApplication.instance() or QApplication([])
    observation={'kind':'series','unit':'N','component':'z','location':'specimen','reduction':'none',
        'axes':[{'name':'time','unit':'s','values':[0.,1.,2.,3.]}],'value':[0.,1.,2.,3.],
        'mask':[True,True,False,True]}
    experiment=experiment_snapshot({'id':'Trial','role':role,'settings':{},'response':'force',
        'observations':observation,'mask':[True,False,True,True],'weight':3.,'scale':2.})
    prediction={key:deepcopy(value) for key,value in observation.items() if key!='mask'}
    prediction['value']=[0.,1.5,2.5,3.5]
    trial=trial_detail(experiment,{'execution_status':'SUCCEEDED','responses':{'force':prediction}},origin={'kind':'controlled_ui'})
    view={'candidate':{'candidate_id':'Cexact','execution_status':'SUCCEEDED'},'attempt_job_id':None,
        'fit_input':{'inputs':{'variables':[],'experiments':[experiment]}},'trials':[trial]}
    original=deepcopy(view)
    window=NumericalCandidateDetailWindow(None,document_id='Ncontrolled',job_id='Jcontrolled',
        candidate_id='Cexact',auto_load=False,poll_interval=10000)
    window.timer.stop();monkeypatch.setattr(window,'_buttons',lambda:None)
    try:
        window.candidates.addItem('후보 1: 계산됨','Cexact');window.view=view
        item=QTreeWidgetItem(['원 시험','피팅' if role=='fit' else '별도 확인'])
        item.setData(0,Qt.ItemDataRole.UserRole,'Trial');window.trials.addTopLevelItem(item)
        window.trials.setCurrentItem(item);window._draw_trial()
        assert '포함 행 3/4, 가중치 3, 척도 2 N' in window.residual_summary.text()
        assert '0.125 [1]' in window.residual_summary.text()
        assert ('목적함수에서 제외' in window.residual_summary.text())==(role=='holdout')
        rows=window.model.rows
        assert not rows[1]['included'] and rows[1]['weighted_residual'] is None
        assert rows[2]['included'] and rows[2]['observation_mask'] is False
        assert rows[2]['raw_residual']==.5 and rows[2]['weighted_residual']==.25
        lines=window.figure.axes[0].lines
        assert math.isnan(lines[0].get_ydata()[1]) and lines[0].get_ydata()[2]==2.
        assert lines[1].get_ydata()[2]==2.5
        assert lines[2].get_label()=='제외한 관측 원값' and lines[2].get_ydata()[1]==1.
        window.curve_mode.setCurrentIndex(2)
        assert window.figure.axes[0].lines[0].get_ydata()[2]==.25
        assert view==original
        # A pending different selection must not retain the previous contribution.
        monkeypatch.setattr(window,'refresh',lambda:None)
        window._selection_changed();assert not window.residual_summary.text()
    finally:
        window.close();QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete);app.processEvents()


@pytest.mark.parametrize('klass',[NumericalWindow,RequestPlanWindow])
def test_failed_penalty_is_a_separate_cell_from_the_fit_objective(klass,monkeypatch):
    app=QApplication.instance() or QApplication([])
    result={'kind':'fit','execution_status':'FAILED','candidates':[
        {'candidate_id':'Cfailed','execution_status':'FAILED','values':{'x':1.},
         'objective':None,'penalty_applied':2.,'failure_reason':'Required prediction missing'}]}
    original=deepcopy(result)
    window=klass(None,auto_open=False,poll_interval=0)
    window.document={'draft':{'mode':'fit'},'runs':[]}
    monkeypatch.setattr(window,'selected_job',lambda:'Jcontrolled')
    window._result_cache['Jcontrolled']=result
    try:
        if klass is NumericalWindow:
            window._draw_result()
        else:
            monkeypatch.setattr(window,'_update_actions',lambda:None)
            window._method_result_view(result)
        headers=[window.candidates.horizontalHeaderItem(i).text() for i in range(window.candidates.columnCount())]
        penalty=headers.index('실패 잔차 벌점 [1]')
        objective=headers.index('잔차 제곱합 [1]')
        assert float(window.candidates.item(0,penalty).text())==2.
        assert window.candidates.item(0,objective).data(Qt.ItemDataRole.UserRole) is None
        assert result==original
    finally:window._allow_close=True;window.close();app.processEvents()


def test_feasibility_remains_the_retained_numerical_verdict(monkeypatch):
    app=QApplication.instance() or QApplication([])
    result={'kind':'optimization','variables':[], 'objective_definition':{'unit':'N'},'candidates':[
        {'candidate_id':'Cinfeasible','execution_status':'SUCCEEDED','values':{},'objective':.01,'feasible':False},
        {'candidate_id':'Cfeasible','execution_status':'SUCCEEDED','values':{},'objective':2.,'feasible':True},
        {'candidate_id':'Cfailed','execution_status':'FAILED','values':{},'objective':None,'failure_reason':'Required prediction missing'}]}
    original=deepcopy(result);window=RequestPlanWindow(None,auto_open=False,poll_interval=0)
    window.document={'draft':{'mode':'request'},'runs':[]}
    monkeypatch.setattr(window,'_update_actions',lambda:None)
    try:
        window._method_result_view(result)
        headers=[window.candidates.horizontalHeaderItem(i).text() for i in range(window.candidates.columnCount())]
        column=headers.index('조건')
        assert [window.candidates.item(i,column).text() for i in range(3)]==['위반','충족','미판정']
        assert float(window.candidates.item(0,column-1).text())==.01
        assert window.candidates.item(2,column-1).data(Qt.ItemDataRole.UserRole) is None
        assert result==original # A smaller but infeasible value is never relabelled feasible.
    finally:window._allow_close=True;window.close();app.processEvents()


def test_request_curve_uses_the_same_retained_mask_and_normalization(monkeypatch):
    app=QApplication.instance() or QApplication([])
    curve={'experiment_id':'Tforce','role':'holdout','observations':{'kind':'series','unit':'N','component':'z',
        'axes':[{'name':'time','unit':'s','values':[0.,1.,2.,3.]}],'value':[0.,1.,2.,3.]},
        'prediction':[0.,None,2.,3.],'mask':[True,False,True,True],'weight':3.,'scale':2.,'rmse':0.}
    result={'kind':'fit','execution_status':'SUCCEEDED','curves':[curve]};original=deepcopy(result)
    window=RequestPlanWindow(None,auto_open=False,poll_interval=0)
    monkeypatch.setattr(window,'selected_job',lambda:'Jretained');window._result_cache['Jretained']=result
    try:
        window._plot_selected_result();axis=window.figure.axes[0]
        assert math.isnan(axis.lines[0].get_ydata()[1]) and axis.lines[2].get_ydata()[1]==1.
        assert '포함 행 3/4, 가중치 3.0, 척도 2.0 N' in axis.get_title()
        assert '목적함수 제외' in axis.get_title() and result==original
    finally:window._allow_close=True;window.close();app.processEvents()
