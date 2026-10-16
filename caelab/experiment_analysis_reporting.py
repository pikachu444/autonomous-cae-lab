"""Human experiment curves, judgments and next questions from SAVED results.

No model calls. Functions create editable draft values only; the caller uses
existing Study/Report document commands, including their normal save/CAS path.
"""
from copy import deepcopy
import math
from .storage import canonical_hash
from .study_document import default_draft, diagnostics
from .experiment_uncertainty import validate_retained_covariance

UNKNOWN = '미확인'
STATES = {'COMPUTED_FIRST_ORDER':'값 조건부 1차 전파', 'UNKNOWN':UNKNOWN, 'EXCLUDED':'제외',
          'LOCAL_RANK_COMPLETE':'국소 독립 방향 충분', 'LOCAL_RANK_DEFICIENT':'국소 미식별 조합 있음',
          'DISTINGUISHABLE_LOCAL':'국소 구분 가능', 'UNRESOLVED_LOCAL':'미식별 조합',
          'SUCCEEDED':'계산 완료', 'FAILED':'실패', 'REJECTED':'실행 차단', 'CANCELLED':'중단 확인',
          'PARTIAL_FAILURE':'부분 계산'}


def value(value):
    return UNKNOWN if value is None or value == 'UNKNOWN' else value


def uncertainty_reason(reason,problem):
    """Translate only the known missing-covariance message; retain raw result."""
    prefix='불확실성/공분산 미제공: '
    if not isinstance(reason,str) or not reason.startswith(prefix):return reason or ''
    labels={}
    for row in problem.get('variables',[]):
        reference=row.get('raw_ref') or {}
        source_row=row.get('source_row',reference.get('source_row'))
        coefficient=row.get('coefficient',row['id'])
        if source_row is not None:
            label='원행 '+str(source_row)
            column=reference.get('column_identity',reference.get('column'))
            if column is not None:label+=' / 열 '+str(column+1 if type(column) is int else column)
        else:label={'a':'기울기 a','x0':'입력 영점','b':'출력 오프셋'}.get(coefficient,'선택 입력')
        if row.get('operand'):label=row['label']+' / '+label
        labels[row['id']]=label
    return prefix+', '.join(' ↔ '.join(labels.get(key,'미확인 입력') for key in pair.split(' ↔ '))
        for pair in reason[len(prefix):].split(', '))


def coordinate(problem):
    original = problem['original']
    if 'axis' in original:
        axis = original['axis']
        return axis['values'], axis.get('name',UNKNOWN)+' ['+axis.get('unit',UNKNOWN)+']'
    raw = original.get('raw_samples', {})
    axis = raw.get('transformed_axis', raw.get('axis'))
    if isinstance(axis, list) and len(axis) == len(problem['values']):
        metadata = (original.get('axes') or [{}])[0]
        return axis, metadata.get('name',UNKNOWN)+' ['+metadata.get('unit',UNKNOWN)+']'
    return raw.get('source_rows', list(range(len(problem['values'])))), '원 행 / 보존 표본 순서 (물리 시각 아님)'


def blocks(result):
    validate_retained_covariance(result)
    a = result.get('experiment_analysis', {})
    p = a.get('source_problem', {})
    yield 'paragraph', STATES.get(result.get('execution_status'), UNKNOWN)+' — 공학적 승인 아님'
    if result.get('failure_reason'):
        yield 'paragraph', str(result['failure_reason'])
    if result.get('kind') == 'experiment_uncertainty':
        difference=p.get('kind')=='comparison_difference'
        value_label='차이 B−A' if difference else '원 교정/처리 값'
        yield 'paragraph', ('저장된 관측 A와 예측 B의 차이 B−A에 대한 1차 전파입니다. 가중·정규화 잔차의 불확실성이 아니며 원 비교는 유지됩니다.' if difference else
            '제공한 입력·계수 불확실성만 사용한 1차 값 전파입니다. 원 교정값과 제공 output uncertainty는 변경하지 않았습니다. 신뢰구간이 아닙니다.')
        yield 'paragraph', ('전체 측정 불확실성: 미확인. 축 불확실성은 계산하지 않았습니다.' if a.get('complete_measurement_uncertainty')=='UNKNOWN'
                            else '선언한 고정 축과 처리 계수에 조건부인 전파입니다.')
        joint = a.get('joint_covariance_validation', {}).get('output', {})
        if joint.get('complete_joint_covariance') == 'UNKNOWN':
            yield 'paragraph', '계산한 표본 사이의 미제공 공분산 관계는 미확인입니다. 알려진 관련 부분행렬만 검증했으며, 누락 관계를 독립 또는 0으로 채우지 않았습니다.'
        yield 'table', (['측정 정보','제공 내용'], [[label,value(p.get('metadata',{}).get(key))] for key,label in
            [('location','측정 위치'),('component','성분'),('direction','방향'),('frame','기준계'),('measure','물리량')]])
        supplied = p.get('supplied_output_uncertainty')
        if isinstance(supplied,dict):
            yield 'table', (['기존 제공 출력 불확실성','단위','종류','포함인자 k','상관'], [[supplied.get('value'),supplied.get('unit'),supplied.get('kind'),value(supplied.get('k')),value(supplied.get('correlation'))]])
        elif isinstance(supplied,list):
            yield 'table', (['원 측정' if difference else '원 교정 적용 순서','제공 출력 불확실성','단위','종류','포함인자 k','상관'],
                [[item.get('operand',i+1),value(u.get('value')),value(u.get('unit')),value(u.get('kind')),value(u.get('k')),value(u.get('correlation'))]
                 for i,item in enumerate(supplied)
                 for u in [item.get('provided_output_uncertainty') if isinstance(item.get('provided_output_uncertainty'),dict) else {}]])
        rows = a.get('rows', []) or [dict(original_value=v,standard_uncertainty=None,unit=p['unit'],
            status='UNKNOWN' if included else 'EXCLUDED',reason=result.get('failure_reason',a.get('reason','미확인')))
            for v,included in zip(p['values'],p['included'])]
        x, label = coordinate(p)
        ids = p.get('original',{}).get('raw_samples',{}).get('source_rows')
        yield 'table', (['원 행' if ids else '표본 순서',value_label,'표준불확실성','단위','판단','사유'],
            [[ids[i] if ids else i+1,r['original_value'],value(r['standard_uncertainty']),r['unit'],STATES.get(r['status'],UNKNOWN),uncertainty_reason(r.get('reason'),p)] for i,r in enumerate(rows)])
        if len(x)==len(p.get('values',[])):
            yield 'curve', {'x':x,'y':p['values'],'mask':p['included'],'x_label':label,'y_label':value_label+' ['+p['unit']+']'}
            yield 'curve', {'x':x,'y':[r['standard_uncertainty'] for r in rows],
                'mask':[r['status']=='COMPUTED_FIRST_ORDER' for r in rows], 'x_label':label,
                'y_label':('차이의 표준불확실성' if difference else '표준불확실성 — 값 조건부 1차')+' ['+p['unit']+']'}
    elif result.get('kind') == 'experiment_identification':
        d = result.get('identification', {})
        yield 'paragraph', STATES.get(d.get('status'),UNKNOWN)+' — 최종 선택점의 일반 잔차 Jacobian 진단입니다. 전역 유일성과 측정 불확실성은 미확인입니다.'
        yield 'table', (['계수','선택 값','단위','역할','국소 구분','경계'],
            [[r['id'],d.get('parameter_values',{}).get(r['id']),r['unit'],'피팅',STATES.get(r.get('status'),UNKNOWN),
              '하한' if r.get('active_bound')==-1 else '상한' if r.get('active_bound')==1 else ''] for r in d.get('parameters',[])]+
            [[r['id'],r.get('value'),r.get('unit'),'고정 (식별 안 함)','대상 아님',''] for r in p.get('fixed_parameters',[])])
        if d.get('singular_values'):
            yield 'curve', {'x':list(range(1,len(d['singular_values'])+1)), 'y':d['singular_values'],
                'x_label':'계수 방향','y_label':'선언 범위로 정규화한 잔차 민감도'}
        # Reuse C1's ONE table/curve reader. Do not resample or recompute fit
        # residuals here, and never use later trial detail for an old attempt.
        from .numerical_candidate_detail import table_rows
        view={'candidate':p['candidate'],'fit_input':p['fit_input'],
              'trials':p['selected_trials'],'attempt_job_id':(p.get('selected_attempt') or {}).get('job_id')}
        experiments=p['fit_input']['inputs']['experiments']
        labels={entry['id']:entry.get('title') or entry.get('name') or '시험 '+str(i+1)
            for i,entry in enumerate(experiments)}
        for t in p.get('selected_trials',[]):
            trial_rows=table_rows(view,t['experiment_id'])
            yield 'paragraph',labels[t['experiment_id']]+' — '+('별도 확인용 (이번 진단에서 평가 안 함)' if t['role']=='holdout' else '피팅용')
            raw_rows=all(type(row.get('source_row')) is int for row in trial_rows)
            if not raw_rows:yield 'paragraph','표본 순서는 보존된 관측 순서이며 원자료의 행 번호가 아닙니다.'
            yield 'table', (['원행' if raw_rows else '표본 순서','관측','보존 예측','원단위 잔차','가중 잔차','포함','단위'],
                [[r['source_row'] if raw_rows else i+1,value(r.get('observation')),value(r.get('prediction')),
                  value(r.get('raw_residual')),value(r.get('weighted_residual')),'포함' if r.get('included') else '제외',r['unit']]
                 for i,r in enumerate(trial_rows)])
            if trial_rows and all(r.get('axis') is not None for r in trial_rows):
                x=[r['axis'] for r in trial_rows];mask=[r['included'] for r in trial_rows]
                for key,label in [('observation','원 관측'),('prediction','보존 예측')]:
                    yield 'curve', {'x':x,'y':[r.get(key) for r in trial_rows],'mask':mask,
                        'x_label':str(trial_rows[0]['axis_name'])+' ['+str(trial_rows[0]['axis_unit'])+']',
                        'y_label':label+' ['+trial_rows[0]['unit']+']'}
        yield 'paragraph', '원 피팅의 실패 기록과 원 holdout은 변경하지 않았습니다. 추가 진단 평가가 원 피팅의 수렴/검증 성공을 소급 부여하지 않습니다.'


def suggested_questions(result):
    """Questions, not automatically accepted conclusions or experiment orders."""
    if result.get('kind')=='experiment_uncertainty':
        a=result['experiment_analysis'];p=a['source_problem']
        questions=[]
        if p.get('kind')=='comparison_difference':
            questions.append('두 측정값의 차이를 판단하려면 A와 B 사이의 공분산·상관을 어떻게 확인해야 하는가?')
        if a.get('missing_input_information') or any(r.get('status')=='UNKNOWN' for r in a.get('rows',[])):
            questions.append('미제공 입력 불확실성·포함인자·상관 중 어떤 자료를 확보해야 해당 표본의 전파를 계산할 수 있는가?')
        if any(p.get('metadata',{}).get(k) in (None,'UNKNOWN') for k in ('location','direction','frame')):
            questions.append('측정 위치·방향·기준계를 확인하면 어떤 비교까지 정당하게 수행할 수 있는가?')
        questions.append('범위 초과·포화·제외 표본이 생긴 시험 조건을 어떻게 변경하거나 재측정할 것인가?')
        return questions
    d=result.get('identification',{})
    if d.get('status')=='LOCAL_RANK_DEFICIENT':
        return ['현재 미식별 계수 조합에 서로 다른 민감도를 주는 하중 경로·측정 응답은 무엇인가?',
                '다음 시험을 독립 검증용으로 보존하고 동일 원행의 재사용을 어떻게 피할 것인가?']
    if d.get('status')=='UNKNOWN':
        return ['차분점 실패·예산·결측·evaluator 변경 중 어떤 원인을 먼저 해결하고 명시 재평가할 것인가?']
    return ['현재 국소 진단을 넘어 다른 초기값·하중 경로에서 동일 판단이 유지되는지 어떤 독립 시험으로 확인할 것인가?']


def study_draft(result, result_reference, *, question, note='', selected_questions=()):
    validate_retained_covariance(result)
    if not isinstance(question,str) or not question.strip():
        raise ValueError('다음 연구 질문을 명시하세요.')
    draft=default_draft();draft['question']=question
    draft['evidence']=[{'id':'Eexperiment','label':'보존한 시험 분석','kind':'result',
        'reference':{'kind':'result',**deepcopy(result_reference)},'note':note}]
    draft['next_observations']=[{'id':'O'+str(i+1),'question':q,'hypothesis_ids':[],
        'evidence_ids':['Eexperiment'],'status':'PLANNED','note':'사용자가 선택한 다음 시험 질문; 자동 실행 없음'}
        for i,q in enumerate(selected_questions)]
    issues=diagnostics(draft)
    if issues:raise ValueError(issues[0]['message'])
    return draft


def retained_report_view(result, selection):
    """An experiment report requires the retained curves/J, not array locators.

    The generic metadata-only reader intentionally does NOT unpack data_ref.
    Its display summary cannot masquerade as a frozen detailed report. The
    existing full hash-verified result supplied by resolve_reference is reused.
    These analyses are bounded (512 samples / 64 fitted parameters); no hidden
    subset is selected and no source/model is read or evaluated here.
    """
    validate_retained_covariance(result)
    if selection != {'metadata_only': True}:
        raise ValueError('시험 분석은 원값·선택·진단을 함께 보존합니다. 임의 행/응답 재선택으로 바꾸지 않습니다.')
    if not isinstance(result.get('experiment_analysis',{}).get('source_problem'),dict):
        raise ValueError('시험 분석의 원값/원후보 상세가 없습니다.')
    return deepcopy(result)


def expert_summary(result):
    """Bounded READ projection, not a replacement for retained detail evidence.

    Co-STORM's existing formatter omits a whole snippet exceeding its word
    budget. Sending a full DAG/J as one JSON snippet silently loses the returned
    calculation. Keep this summary explicitly incomplete, with original result
    identity/limitations; actual comparison/adoption/report gates still require
    their original immutable evidence. Other result kinds are not changed.
    """
    from .experiment_uncertainty import plain
    if result.get('kind') not in {'experiment_uncertainty','experiment_identification'}:
        return None
    validate_retained_covariance(result)
    a=result.get('experiment_analysis',{});p=a.get('source_problem',{})
    def label(value):
        text=str(value)
        return text if len(text)<=96 else text[:96]+' [표시 생략]'
    summary={'kind':result['kind'],'execution_status':result.get('execution_status','UNKNOWN'),
        'reading_scope':'BOUNDED_SUMMARY_ONLY; full retained detail required for comparison/adoption/success report',
        'source_result_sha256':canonical_hash(plain(result)),
        'measurement_uncertainty':'UNKNOWN','global_uniqueness':'UNKNOWN','engineering_release':'NOT_RELEASED'}
    if result['kind']=='experiment_uncertainty':
        rows=a.get('rows',[])
        summary.update(measurement_uncertainty_source=a.get('measurement_uncertainty_source','UNKNOWN'),
            value_scope=a.get('scope','UNKNOWN'),complete_measurement_uncertainty=a.get('complete_measurement_uncertainty','UNKNOWN'),
            sample_count=len(p.get('values',[])),included_count=sum(p.get('included',[])),
            unit=label(p.get('unit','UNKNOWN')),calibration_reapplied=False,
            preview_rows=[{'sample_order':i+1,'original_value':r.get('original_value'),
                'standard_uncertainty':r.get('standard_uncertainty'),'status':r.get('status','UNKNOWN')}
                for i,r in enumerate(rows[:8])],
            full_original_rows_and_masks='RETAINED_NOT_REPLACED',
            joint_output_covariance=a.get('joint_covariance_validation',{}).get('output',{}).get('complete_joint_covariance','UNKNOWN'),
            correlations='provided only; missing correlations not independent/zero',
            confidence_interval='UNKNOWN')
        summary['preview_rows_omitted']=max(0,summary['sample_count']-len(summary['preview_rows']))
    else:
        d=result.get('identification',{})
        summary.update(local_diagnosis=d.get('status','UNKNOWN'),jacobian_rank=d.get('jacobian_rank'),
            coefficient_count=len(p.get('variables',[])),relative_rank_tolerance=d.get('relative_rank_tolerance'),
            parameters=[{'parameter':label(v['id']),'unit':label(v['unit']),
                'selected_value':p.get('candidate',{}).get('values',{}).get(v['id']),
                'active_bound':next((r.get('active_bound') for r in d.get('parameters',[]) if r['id']==v['id']),None)}
                for v in p.get('variables',[])[:8]],
            parameter_preview_omitted=max(0,len(p.get('variables',[]))-8),
            fixed_parameter_count=len(p.get('fixed_parameters',[])),
            ordinary_jacobian_retained=a.get('ordinary_jacobian') is not None,
            original_fit_status=p.get('original_fit_status','UNKNOWN'),
            original_fit_holdout='UNCHANGED; not re-evaluated or retroactively filled')
    if result.get('failure_reason'):summary['failure_reason']=label(result['failure_reason'])
    return summary
