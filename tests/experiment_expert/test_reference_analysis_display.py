"""Presentation of a retained analysis; no owner, solver or inference exists."""
from copy import deepcopy
import pytest
pytest.importorskip('PySide6')
from PySide6.QtWidgets import QApplication
from apps.research.reference_content import ReferenceContent


def test_saved_final_diagnosis_uses_existing_report_tables_in_study_reader():
    app=QApplication.instance() or QApplication([])
    result={'kind':'experiment_identification','execution_status':'SUCCEEDED','responses':{},
        'identification':{'status':'LOCAL_RANK_COMPLETE','parameter_values':{'mu':7.},
            'parameters':[{'id':'mu','unit':'MPa','status':'DISTINGUISHABLE_LOCAL'}]},
        'experiment_analysis':{'source_problem':{'candidate':{},
            'fit_input':{'inputs':{'experiments':[]}},'selected_trials':[]}}}
    payload={'kind':'result','status':'AVAILABLE','result':result,'metadata':{'responses':[]},
        'reference':{'kind':'result','job_id':'Jprivate'}}
    original=deepcopy(payload);content=ReferenceContent()
    try:
        content.set_payload(payload,label='선택한 시험 진단')
        text=content.body.toPlainText()
        assert '국소 독립 방향 충분' in text and '일반 잔차 Jacobian' in text
        assert 'MPa' in text and 'mu' in text and '7' in text
        assert '공학적 승인 아님' in text
        from apps.research.report_pages import blocks
        first=next(value for kind,value in blocks(payload) if kind=='paragraph')
        assert content.body.document().firstBlock().text()==first
        assert content.body.document().documentMargin()==6
        assert 'Jprivate' not in text and 'experiment_analysis' not in text
        assert content.result_views.isHidden() and content.channel.isHidden()
        assert payload==original
    finally:content.close();content.deleteLater();app.processEvents()
