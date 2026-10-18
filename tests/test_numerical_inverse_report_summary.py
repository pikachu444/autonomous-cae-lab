"""Rendering uses frozen residual rows; no fit or evidence admission is simulated."""
from copy import deepcopy
import pytest
from test_numerical_candidate_report_presentation import presentation
from apps.research import numerical_candidate_evidence_report as report


@pytest.mark.parametrize('role',['fit','holdout'])
def test_report_states_frozen_inclusion_weight_scale_and_holdout_exclusion(presentation,role):
    content,rows=presentation
    rows[0].update(weight=3.,scale=2.)
    excluded=deepcopy(rows[0]);excluded.update(source_row=13,included=False,
        prediction=None,raw_residual=None,weighted_residual=None)
    rows.append(excluded)
    content['candidate_evidence']['snapshot']['trials'][0]['role']=role
    original=deepcopy(content);original_rows=deepcopy(rows)
    text='\n'.join(value for kind,value in report.candidate_evidence_blocks(content) if kind=='paragraph')
    assert '포함 행 1/2, 가중치 3, 척도 2 MPa' in text
    assert ('목적함수에서 제외' in text)==(role=='holdout')
    assert content==original and rows==original_rows


def test_missing_summary_metadata_is_not_fabricated_zero(presentation):
    content,_rows=presentation
    text='\n'.join(value for kind,value in report.candidate_evidence_blocks(content) if kind=='paragraph')
    assert '가중치 미제공, 척도 미제공 MPa' in text
