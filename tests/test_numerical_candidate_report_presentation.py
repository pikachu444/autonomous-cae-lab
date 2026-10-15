"""Presentation only: scripted rows do not certify Numerical evidence admission."""
from copy import deepcopy

import pytest

from apps.research import numerical_candidate_evidence_report as report


@pytest.fixture
def presentation(monkeypatch):
    rows = [dict(source_row=12, sample_id='Sprivate-sample', axis=.25, unit='MPa',
        observation=2., prediction=2.1, raw_residual=.1, weighted_residual=.05,
        included=True, observation_mask=True, axis_name='time', axis_unit='s')]
    snapshot = {'purpose': report.SUCCESS, 'source': {'job_id': 'Jprivate-origin', 'result_sha256': 'a'*64},
        'original_candidate': {'candidate_id': 'Cprivate-candidate', 'execution_status': 'SUCCEEDED', 'values': {'E': 100.}},
        'selected_attempt_job_id': 'Jprivate-detail', 'candidate_sha256': 'b'*64,
        'fit_input': {'inputs_sha256': 'c'*64, 'inputs': {'experiments': [
            {'id': 'Eprivate-fit', 'name': '인장 시험', 'role': 'fit'},
            {'id': 'Eprivate-holdout', 'role': 'holdout'}]}},
        'scope': [{'experiment_id': 'Eprivate-fit', 'response': 'stress_xx', 'role': 'fit'}],
        'trials': [{'experiment_id': 'Eprivate-fit', 'role': 'fit', 'execution_status': 'SUCCEEDED',
                    'retention': 'RETAINED', 'raw_evaluation': {}}],
        'trial_refs': [{'experiment_id': 'Eprivate-fit', 'job_id': 'Jprivate-detail', 'raw_sha256': 'd'*64}],
        'original_fit_holdout_sha256': 'e'*64}
    content = {'kind': 'numerical_candidate_evidence', 'candidate_evidence': {
        'snapshot': snapshot, 'reference': {'snapshot_sha256': 'f'*64, 'attempt_chain_sha256': '1'*64},
        'readiness': {'preservation': 'IMMUTABLE_REVISION_VERIFIED', 'failure_records': []}}}
    monkeypatch.setattr(report, 'table_rows', lambda *_args: deepcopy(rows))
    return content, rows


def test_report_keeps_physics_and_subset_scope_with_exact_ids_only_in_optional_diagnostics(presentation):
    content, rows = presentation
    before = deepcopy(content)
    blocks = list(report.candidate_evidence_blocks(content))
    visible = str([block if kind != 'curve' else (block['x_label'], block['y_label'])
                   for kind, block in blocks])
    assert '선택 후보 결과' in visible and '인장 시험' in visible and '전체 시험 평가를 뜻하지 않습니다' in visible
    assert '공학 승인은 미확인' in visible and '파생 표본의 독립성: 미확인' in visible
    assert not any(token in visible for token in ('Jprivate-', 'Cprivate-', 'Sprivate-', 'Eprivate-', 'SHA256', 'IMMUTABLE_REVISION_VERIFIED', 'a'*64))
    assert any(kind == 'curve' and block['y'] == [2.1] for kind, block in blocks)
    diagnostics = report.candidate_evidence_diagnostics(content)
    assert diagnostics['source']['job_id'] == 'Jprivate-origin'
    assert diagnostics['trial_refs'][0]['raw_sha256'] == 'd'*64
    diagnostics['source']['job_id'] = 'changed optional view'
    assert content == before


def test_failed_response_stays_absent_without_prediction_curve_or_success_wording(presentation):
    content, rows = presentation
    evidence = content['candidate_evidence']; snapshot = evidence['snapshot']
    snapshot['purpose'] = 'failure_diagnostic'
    snapshot['original_candidate']['execution_status'] = 'FAILED'
    snapshot['trials'][0].update(execution_status='FAILED', retention='NOT_EVALUATED')
    evidence['readiness']['failure_records'] = [{'state': 'FAILED', 'reason': '보존된 평가 오류'}]
    rows[0].update(prediction=None, raw_residual=None, weighted_residual=None)
    blocks = list(report.candidate_evidence_blocks(content))
    assert '선택 후보 실패·취소 기록' in str(blocks) and '보존된 평가 오류' in str(blocks)
    assert not any(kind == 'curve' and '예측' in block['y_label'] for kind, block in blocks)
    table = next(value for kind, value in blocks if kind == 'table' and value[0][0] == '원행')
    assert table[1][0][3:6] == [None, None, None]


def test_derived_display_uses_sample_order_and_only_verified_consumer_scope(presentation):
    content, rows = presentation
    rows[0]['source_row']=None
    original=deepcopy(content);original_rows=deepcopy(rows)
    blocks=list(report.candidate_evidence_blocks(content))
    table=next(value for kind,value in blocks if kind=='table' and value[0][0]=='표본 순서')
    assert table[1][0][0]==1 and '원자료의 행 번호가 아닙니다' in str(blocks)
    assert 'Sprivate-sample' not in str(table)
    assert content==original and rows==original_rows
    content['candidate_evidence']['readiness']['lineage']={
        'status':'CANONICAL_DATA_CONSUMER_VERIFIED',
        'derived_sample_independence':'VERIFIED_DISJOINT_RAW_VALUE_CONTRIBUTORS'}
    paragraphs=[value for kind,value in report.candidate_evidence_blocks(content) if kind=='paragraph']
    assert '피팅과 별도 확인 간 중복 없음' in str(paragraphs)
    assert '측정오차의 상관은 미확인' in str(paragraphs)
    # Partial/legacy labels and unverified preservation never become success.
    content['candidate_evidence']['readiness']['lineage']['status']='LEGACY_SOURCE_ROW_CHECK_ONLY'
    assert '파생 표본의 독립성: 미확인' in str(list(report.candidate_evidence_blocks(content)))
    content['candidate_evidence']['readiness']['lineage']['status']='CANONICAL_DATA_CONSUMER_VERIFIED'
    content['candidate_evidence']['readiness']['preservation']='UNKNOWN'
    assert '파생 표본의 독립성: 미확인' in str(list(report.candidate_evidence_blocks(content)))
