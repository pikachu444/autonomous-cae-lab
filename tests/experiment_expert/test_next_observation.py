"""Read/choose only: labeled saved-record presentation fixtures, no evaluator."""
import os
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from copy import deepcopy
import pytest
pytest.importorskip('PySide6')
from PySide6.QtCore import Qt,QTimer
from PySide6.QtWidgets import QApplication,QDialogButtonBox,QMessageBox
from apps.research.experiment_followup_dialog import NextObservationDialog
from apps.research.experiment_analysis_window import ExperimentAnalysisWindow
from caelab.experiment_analysis_reporting import blocks,diagnosis_tables


def saved_record():
    return {'kind':'experiment_identification','execution_status':'SUCCEEDED','identification':{
        'status':'LOCAL_RANK_DEFICIENT','parameter_values':{'x':1.25,'y':.5},
        'parameters':[{'id':key,'unit':'N','status':'UNRESOLVED_LOCAL'} for key in ('x','y')],
        'null_directions':[[.707,-.707]],'singular_values':[2.,0.]},
        'experiment_analysis':{'source_problem':{'candidate':{},'selected_trials':[],
            'fixed_parameters':[{'id':'area','value':10.,'unit':'mm2'}],
            'fit_input':{'inputs':{'experiments':[{'id':'Tfit','title':'하중 시험','role':'fit','response':'force','observations':{'unit':'N'}},
                {'id':'Thold','title':'독립 시험','role':'holdout','response':'force','observations':{'unit':'N'}}]}}}}}


def test_question_has_no_default_and_selected_existing_observation_remains_holdout():
    app=QApplication.instance() or QApplication([])
    result=saved_record();before=deepcopy(result);dialog=NextObservationDialog(result)
    try:
        dialog.show();dialog.activateWindow();app.processEvents()
        assert dialog.questions.currentRow()==-1 and not dialog.question.toPlainText()
        assert not dialog.buttons.button(QDialogButtonBox.StandardButton.Save).isEnabled()
        dialog.questions.setCurrentRow(1)
        assert dialog.question.toPlainText()==dialog.questions.item(1).text()
        dialog.question.setPlainText('다른 방향 하중으로 x와 y를 구별할 수 있는가?')
        dialog.observations.item(1).setCheckState(Qt.CheckState.Checked)
        dialog.note.setPlainText('고정 면적은 이번 진단에서 식별하지 않았다.')
        selected=dialog.selection()
        assert selected['observation_ids']==['Thold'] and '별도 확인' in selected['note']
        assert '2. 독립 시험' in selected['note']
        assert '고정 면적' in selected['note'] and 'x와 y' in selected['question']
        assert dialog.buttons.button(QDialogButtonBox.StandardButton.Save).isEnabled()
        assert result==before
    finally:dialog.close();dialog.deleteLater();app.processEvents()


def test_saved_direction_and_fixed_rows_reach_report_without_new_judgment():
    result=saved_record();before=deepcopy(result)
    coefficients,directions=diagnosis_tables(result)
    assert coefficients[1][-1]==['area',10.,'mm2','고정 (식별 안 함)','대상 아님','']
    assert directions==(['보존 방향','x','y'],[[1,.707,-.707]])
    content=list(blocks(result))
    assert ('table',directions) in content
    result['execution_status']='FAILED';result['failure_reason']='보존한 차분점 실패'
    result['identification']={'status':'UNKNOWN','reason':'원 잔차 재현 불일치'}
    failed=str(list(blocks(result)))
    assert '보존한 차분점 실패' in failed and '원 잔차 재현 불일치' in failed and '미확인' in failed
    result['execution_status']=before['execution_status'];result.pop('failure_reason');result['identification']=before['identification']
    assert result==before


def test_reading_diagnosis_keeps_coefficient_selection_and_unapplied_input(monkeypatch):
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr(ExperimentAnalysisWindow,'_call',lambda *args,**kwargs:False)
    window=ExperimentAnalysisWindow(object(),source={'kind':'result_response','reference':{},'response':'force'})
    try:
        window._view={'problem':{}};window.document={'id':'Nretained'};window.job_id='Jretained'
        result=saved_record();window._show_result(result)
        assert window.coefficients.rowCount()==3 and window.directions.rowCount()==1
        window.coefficients.setCurrentCell(2,0);window.coefficients.item(2,0).setSelected(True)
        window.dirty=True;window.dependence_note.setText('현재 미적용 입력')
        window._show_result(deepcopy(result))
        assert window.coefficients.currentRow()==2 and window.coefficients.item(2,0).isSelected()
        assert window.dependence_note.text()=='현재 미적용 입력' and window.dirty
        assert '현재 편집 입력과 다를 수 있습니다' in window.message.text()
    finally:
        window.dirty=False;window.close();window.deleteLater();app.processEvents()


def test_followup_pins_the_shown_result_while_another_job_is_pending(monkeypatch):
    app=QApplication.instance() or QApplication([])
    import apps.research.experiment_analysis_window as module
    monkeypatch.setattr(ExperimentAnalysisWindow,'_call',lambda *args,**kwargs:False)
    window=ExperimentAnalysisWindow(object(),source={'kind':'result_response','reference':{},'response':'force'})
    try:
        window.document={'id':'Nretained','session_id':'Ssession'}
        window.job_id='Jshown';window._show_result(saved_record())
        window.job_id='Jnew_pending'
        reads=[]
        class Client:
            def document_result_reference(self,*args):reads.append(args);return {}
        window.client=Client();window._call=lambda fn,done,**kwargs:fn()
        window._report();assert reads==[('Nretained','Jshown')]
        monkeypatch.setattr(module,'choose_next_observation',lambda *_:{'question':'직접 선택한 다음 시험','note':''})
        monkeypatch.setattr(module,'save_analysis_study',lambda client,pending:None)
        window._study()
        assert window._study_pending['source_job']=='Jshown'
        assert window.job_id=='Jnew_pending' and window._shown_job_id=='Jshown'
        callbacks=[]
        window._call=lambda fn,done,**kwargs:callbacks.append(done)
        window._report();window._shown_job_id='Jnew_shown'
        callbacks[-1]({})
        assert not window._children and '표시한 진단이 바뀌었습니다' in window.message.text()
        window._study();pending=window._study_pending
        window._shown_job_id='Janother_shown';callbacks[-1]({'document':{}})
        assert window._study_pending is pending and not window._children
    finally:
        window.dirty=False;window._study_pending=None;window.close();window.deleteLater();app.processEvents()


def test_actual_modal_preserves_a_question_when_nested_poll_shows_b(monkeypatch):
    app=QApplication.instance() or QApplication([])
    monkeypatch.setattr(ExperimentAnalysisWindow,'_call',lambda *args,**kwargs:False)
    window=ExperimentAnalysisWindow(object(),source={'kind':'result_response','reference':{},'response':'force'})
    try:
        window.document={'id':'Nretained','session_id':'Ssession'}
        window.job_id='JA';window._show_result(saved_record());window.show()
        dispatched=[];window._call=lambda fn,done,**kwargs:dispatched.append(fn)
        def nested_poll():
            dialog=app.activeModalWidget()
            if not isinstance(dialog,NextObservationDialog):QTimer.singleShot(5,nested_poll);return
            dialog.question.setPlainText('원 A의 관측으로 구별할 다음 시험')
            dialog.observations.item(0).setCheckState(Qt.CheckState.Checked)
            changed=saved_record();changed['identification']['parameter_values']['x']=3.
            window.job_id='JB';window._show_result(changed)
            dialog.buttons.button(QDialogButtonBox.StandardButton.Save).click()
        QTimer.singleShot(10,nested_poll);window._study()
        assert window._study_pending['source_job']=='JA'
        assert window._study_pending['question']=='원 A의 관측으로 구별할 다음 시험'
        assert window._study_pending['requires_confirmation'] and not dispatched
        assert window._shown_job_id=='JB' and not window._children
        monkeypatch.setattr(QMessageBox,'question',lambda *args,**kwargs:QMessageBox.StandardButton.Cancel)
        window._study()
        assert window._study_pending['requires_confirmation'] and not dispatched
        monkeypatch.setattr(QMessageBox,'question',lambda *args,**kwargs:QMessageBox.StandardButton.Save)
        window._study()
        assert len(dispatched)==1 and window._study_pending['source_job']=='JA'
        assert not window._study_pending.get('requires_confirmation')
    finally:
        window.dirty=False;window._study_pending=None;window.close();window.deleteLater();app.processEvents()
