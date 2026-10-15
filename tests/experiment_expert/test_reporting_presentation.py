"""Presentation of exact retained IDs/rows only; no numerical admission claim."""
from copy import deepcopy
from caelab.experiment_analysis_reporting import blocks,uncertainty_reason


def test_derived_trial_is_numbered_without_claiming_a_raw_row_or_displaying_ids(monkeypatch):
    import caelab.numerical_candidate_detail as detail
    rows=[{'source_row':None,'sample_id':'Pprivate','observation':2.,'prediction':2.1,
        'raw_residual':.1,'weighted_residual':.05,'included':True,'unit':'N'}]
    monkeypatch.setattr(detail,'table_rows',lambda *_:deepcopy(rows))
    result={'kind':'experiment_identification','execution_status':'SUCCEEDED','identification':{'status':'UNKNOWN'},
        'experiment_analysis':{'source_problem':{'candidate':{},'fit_input':{'inputs':{'experiments':[
            {'id':'Eprivate','role':'fit','name':'인장 시험'}]}},'selected_trials':[{'experiment_id':'Eprivate','role':'fit'}]}}}
    before=deepcopy(result);rendered=list(blocks(result));text=str(rendered)
    table=next(v for k,v in rendered if k=='table' and v[0][0]=='표본 순서')
    assert table[1][0][0]==1 and table[1][0][1:5]==[2.,2.1,.1,.05]
    assert '인장 시험' in text and '원자료의 행 번호가 아닙니다' in text
    assert 'Eprivate' not in text and 'Pprivate' not in text
    assert result==before


def test_missing_covariance_reason_uses_reading_labels_and_original_remains_exact():
    reason='불확실성/공분산 미제공: raw:private ↔ cal:private:a'
    problem={'variables':[{'id':'raw:private','raw_ref':{'source_row':12,'column_identity':'voltage'}},
        {'id':'cal:private:a','coefficient':'a'}]}
    assert uncertainty_reason(reason,problem)=='불확실성/공분산 미제공: 원행 12 / 열 voltage ↔ 기울기 a'
    assert reason=='불확실성/공분산 미제공: raw:private ↔ cal:private:a'
