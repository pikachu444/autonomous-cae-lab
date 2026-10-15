"""Semantic report blocks from the exact Numerical snapshot (no Qt or solver).

ReportPages renders these using its existing native preview/print/export path.
The failed diagnostic path includes absent values and failed raw receipts; it
never renders them as a successful response or as zeros.
"""
from copy import deepcopy
import json

from caelab.numerical_candidate_detail import table_rows
from caelab.numerical_candidate_evidence import _snapshot_view, SUCCESS


def _state(value):
    return {'SUCCEEDED': '계산 완료', 'FAILED': '계산 실패', 'CANCELLED': '계산 취소',
        'PARTIAL_FAILURE': '일부 계산 실패', 'INTERRUPTED': '계산 중단', 'REJECTED': '계산 불가',
        'NOT_RETAINED': '상세 미보존', 'RETAINED': '상세 보존',
        'PARTIAL_OUTPUT': '출력 일부 보존', 'NOT_EVALUATED': '평가하지 않음'}.get(value, '미확인')


def _reason(value):
    if isinstance(value, str):
        return value
    if isinstance(value, dict):
        return next((_reason(value[key]) for key in ('message', 'reason', 'failure_reason', 'error')
                     if value.get(key)), '상세 진단은 선택 결과 진단에서 확인하세요.')
    return '응답 없음' if value is None else '상세 진단은 선택 결과 진단에서 확인하세요.'


def candidate_evidence_blocks(content):
    evidence = content['candidate_evidence']
    snapshot, readiness = evidence['snapshot'], evidence['readiness']
    candidate = snapshot['original_candidate']
    success = snapshot['purpose'] == SUCCESS
    label = '선택 후보 결과' if success else '선택 후보 실패·취소 기록'
    preserved = ('저장한 결과를 확인했습니다.' if readiness['preservation'] == 'IMMUTABLE_REVISION_VERIFIED'
                 else '저장 상태 미확인')
    yield ('paragraph', label + '\n원 후보: ' + _state(candidate.get('execution_status')) +
           ' / ' + ('선택한 추가 계산 결과' if snapshot['selected_attempt_job_id'] else '원 피팅에 보존된 결과') +
           '\n' + preserved + '\n별도 확인 시험의 합격·계수 식별 성공·공학 승인은 미확인입니다.' +
           '\n파생 표본의 독립성: 미확인')
    experiments = snapshot['fit_input']['inputs']['experiments']
    labels = {entry['id']: entry.get('title') or entry.get('name') or '시험 ' + str(index + 1)
              for index, entry in enumerate(experiments)}
    roles = {'fit': '피팅', 'holdout': '별도 확인'}
    yield ('paragraph', '보고 범위: ' + ', '.join(labels[e['experiment_id']] +
           ' (' + roles.get(e['role'], '역할 미확인') + ', ' + e['response'] + ')' for e in snapshot['scope']) +
           ('\n선택한 시험의 결과이며 전체 시험 평가를 뜻하지 않습니다.'
            if len(snapshot['scope']) != len(experiments) else ''))
    if candidate.get('values'):
        yield ('table', (['계수', '선택한 값'], list(candidate['values'].items())))
    if not success:
        for failure in readiness['failure_records']:
            yield ('paragraph', '실패 기록: ' + _state(failure.get('state')) + ' / ' + _reason(failure))
    view = _snapshot_view(snapshot)
    required = {e['experiment_id'] for e in snapshot['scope']}
    for trial in snapshot['trials']:
        if trial['experiment_id'] not in required:
            continue
        rows = table_rows(view, trial['experiment_id'])
        trial_label = labels[trial['experiment_id']]
        text = (trial_label + ' / ' + roles.get(trial['role'], '역할 미확인') + ' / ' +
                _state(trial['execution_status']) + ' / ' + _state(trial['retention']))
        if trial['role'] == 'holdout':
            text += '\n추가 확인 결과는 원 피팅 당시의 별도 확인 기록과 구분하여 보존했습니다.'
        yield ('paragraph', text)
        raw = trial.get('raw_evaluation') or {}
        if trial.get('execution_status') != 'SUCCEEDED':
            yield ('paragraph', '계산 진단: ' + _reason(raw.get('diagnostics', (trial.get('curve') or {}).get('failure_reason'))))
        unit = rows[0]['unit']
        included = lambda value: '포함' if value is True else ('제외' if value is False else '미확인')
        quality = lambda value: '유효' if value is True else ('무효' if value is False else '미확인')
        yield ('table', (['원행', '축', '관측 [' + unit + ']', '예측 [' + unit + ']',
            '원단위 잔차 [' + unit + ']', '정규화 잔차 [1]', '피팅 사용', '관측 품질'],
            [[r.get('source_row'), r.get('axis'), r['observation'], r['prediction'],
              r['raw_residual'], r['weighted_residual'], included(r['included']), quality(r['observation_mask'])] for r in rows]))
        if rows[0].get('axis_name') is not None:
            for key, label in [('observation', '관측'), ('prediction', '예측'), ('raw_residual', '원단위 잔차')]:
                if key != 'observation' and not any(r[key] is not None for r in rows):
                    continue
                yield ('curve', {'x': [r['axis'] for r in rows], 'y': [r[key] for r in rows],
                    'mask': [True if key == 'observation' else r['included'] for r in rows],
                    'source_rows': [r.get('sample_id') or r.get('source_row') for r in rows],
                    'x_label': rows[0]['axis_name'] + ' [' + str(rows[0]['axis_unit']) + ']',
                    'y_label': trial_label + ' / ' + label + ' [' + unit + ']'})


def candidate_evidence_diagnostics(content):
    """Exact identifiers remain available only in explicitly opened diagnostics."""
    evidence = content['candidate_evidence']
    snapshot = evidence['snapshot']
    return deepcopy({'reference': evidence['reference'], 'source': snapshot['source'],
        'candidate_id': snapshot['original_candidate']['candidate_id'],
        'candidate_sha256': snapshot['candidate_sha256'],
        'fit_input_sha256': snapshot['fit_input']['inputs_sha256'],
        'original_fit_holdout_sha256': snapshot['original_fit_holdout_sha256'],
        'trial_refs': snapshot['trial_refs'], 'readiness': evidence['readiness']})


def show_candidate_diagnostics(window):
    from PySide6.QtWidgets import QDialog, QDialogButtonBox, QPlainTextEdit, QVBoxLayout
    index = window.sections.currentRow()
    if index < 0:
        window.message.setText('진단을 확인할 계산 결과 섹션을 선택하세요.'); return
    binding = window.draft['sections'][index].get('asset') or {}
    asset = window.assets.get(binding.get('id'), {})
    content = asset.get('content', {})
    if content.get('kind') != 'numerical_candidate_evidence':
        window.message.setText('선택 후보 결과 섹션에서 진단을 확인할 수 있습니다.'); return
    dialog = QDialog(window); dialog.setWindowTitle('선택 결과 진단'); dialog.resize(820, 620)
    layout = QVBoxLayout(dialog)
    details = QPlainTextEdit(); details.setReadOnly(True)
    details.setPlainText(json.dumps(candidate_evidence_diagnostics(content), ensure_ascii=False, indent=2))
    layout.addWidget(details)
    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    buttons.button(QDialogButtonBox.StandardButton.Close).setText('보고서로 돌아가기')
    buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
    dialog.exec()
