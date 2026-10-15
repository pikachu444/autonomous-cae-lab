# API와 실제 연결 계약

새 backend가 아니라 기존 Numerical Request Plan의 두 operation이다.
원 API/소유의 기준은 첨부 API_MAP.md이며 Data/Numerical C2는 별도 통합 대상이다.
아래 예시의 `source`, `reference`는 기존 owner가 실제 반환한 객체를 사용한다.
ID/hash를 임의 작성하거나 현재 문서로 과거 결과를 대체하지 않는다.

## 1. 원 시험 읽기와 명시 전파

```python
from caelab.experiment_analysis_actions import read_analysis_source, ExplicitAnalysisAction
from caelab.experiment_analysis_service import uncertainty_request

# 기존 WorkbenchClient의 읽기. 계산/새 Plan 생성 없음.
reference = client.document_result_reference(data_document_id, original_job_id)
source = {
    "kind": "result_response", "reference": reference,
    "response": selected_response_name,
}
view = read_analysis_source(client, source=source)
# view.problem.variables의 id/unit을 그대로 사용한다. 기본값은 미제공이다.
specification = {
    "uncertainties": {
        row["id"]: {"kind": "UNKNOWN", "value": None, "unit": row["unit"]}
        for row in view["problem"]["variables"]
    },
    "dependence": {"kind": "UNKNOWN"},
    "axis_uncertainty": "UNKNOWN",
}
# 사용자가 실제 증빙에서 입력한 값만 specification에 반영한다.
request = uncertainty_request(source, specification)
action = ExplicitAnalysisAction(request, "run", source_reference=view["source_reference"],
                                session_id=view["session_id"])
receipt = action.perform(client)  # 이 지점에서만 기존 numerical.run을 제출한다.
# 응답 유실 시 action 객체를 보존하고 같은 perform을 다시 호출한다.
# 새 action을 생성해 같은 작업을 중복 제출하지 않는다.
```

읽기 reference는 기존 다섯 필드 `document_id/job_id/input_revision/input_sha256/
result_sha256`다. owner가 원 문서/작업/입력/결과를 검증한다. 저장만 하는 경우
`action="save"`로 바꾼다. 기존 Plan schema의 양수 budget slot 때문에 전파는
`budget.evaluations=1`을 사용하지만 실제 모델/솔버/provider 호출은 **0회**다.

기존 분석 문서 편집은 `ExplicitAnalysisAction(..., document=actual_document)`로
원 generation을 전달한다. create/update/finish command ID 및 payload는 재시도
동안 고정된다. conflict 후 최신 generation으로 몰래 덮어쓰지 않는다.

### 제공 값의 형식

`uncertainties[id]`는 다음 중 하나다.

```json
{"kind":"standard","value":0.02,"unit":"N","source":{"certificate":"사용자가 제공한 증빙"}}
```

```json
{"kind":"expanded","value":0.04,"unit":"N","k":2,"note":"제공 U와 k"}
```

`value:null`, `kind:UNKNOWN`, 확장 U의 `k:null`은 계산에 필요한 해당 항목을
UNKNOWN으로 남긴다. 단위는 기존 calibration 단위 또는 그 단위의 한 번의
비율만 지원한다. coefficient 단위 예: `N/mV`. 차원이 다른 변환은 거절한다.

`dependence`는 `{"kind":"UNKNOWN"}`, 또는 정확 변수 순서/행렬을 가진 아래
두 형식이다. `matrix`의 null은 미제공이다. covariance는 각 행·열의 단위 곱,
correlation은 무차원이다. `order`는 정확한 전체 variable id 순서여야 한다.

```python
covariance = {"kind": "covariance", "order": variable_ids,
              "units": variable_units, "matrix": supplied_covariance, "note": supplied_note}
correlation = {"kind": "correlation", "order": variable_ids,
               "matrix": supplied_correlation, "note": supplied_note}
```

독립성을 실제로 선언할 때만 `{"kind":"independent_declared","note":"선언 근거"}`를
쓴다. 누락된 상관을 이 값으로 자동 채우지 않는다. covariance 단위와 각 표준
불확실성의 단위는 독립적으로 변환·대조하므로 UI에서 원 covariance 단위를 유지한다.

`axis_uncertainty`는 기본 `UNKNOWN`, 또는 명시 `fixed_coordinates_declared`다.
다른 요청은 지원하지 않는 축 전파다. 후자는 축 고정 선언이지 실제 측정 확실성의
입증이 아니다. `plan_mask`는 원 출력 수와 같은 길이의 boolean 배열이다.

## 2. Data 처리 개정

```python
source = {"kind": "processing_channel", "document_id": data_document_id,
          "revision": published_processing_revision, "channel": published_channel_key,
          "channel_sha256": exact_published_channel_hash}
view = read_analysis_source(client, source=source)
```

`revision`은 처리 개정이지 Data의 현재 generation이나 원 결과 끝 시각이 아니다.
서버는 실제 `data_processing_document.result(owner,id,revision)`를 읽고 채널 hash를
대조한다. client는 기존 authenticated `/api/workbench/data-material`의
`data.processing.result`를 재사용한다. 원 result reference는 기존 result→Plan
receipt의 anchor이며, 처리 개정/채널은 별도로 Plan에 그대로 동결된다.

처리 결과 객체를 클라이언트가 임의 만들어 실행 요청에 넣는 API는 제공하지 않는다.
`trace_sample`의 실제 원 signed terms와 원 import application 계수를 소비하며
Data C2의 freeze/consume/canonical transport 파일은 변경하지 않는다.

## 3. 최종 선택 후보의 진단

```python
from caelab.experiment_analysis_service import final_request

# reference는 기존 numerical.evidence.capture 성공 응답에서 받은 불변 ref.
# candidate_id만으로 현재 best/최근 성공 attempt를 임의 선택하지 않는다.
view = read_analysis_source(client, evidence_reference=reference)
request = final_request(reference, evaluations=view["model_evaluations"])
action = ExplicitAnalysisAction(request, "run", source_reference=view["source_reference"],
                                session_id=view["session_id"])
receipt = action.perform(client)
```

기본 간격의 `view.model_evaluations`는 비용 미리보기다. 다른 `relative_step`은
`prepare_request`/원 Plan preview의 실제 비용을 확인한다. budget은 사용자가 명시한
정수이며 부족하면 새로운 진단은 0 평가로 거절된다. 부족한 비용을 자동 증액하지 않는다.
원 자료가 실패/미보존이어서 진단 불가인 경우 미리보기의 0을 곧바로 budget으로
제출하지 않는다. 기존 schema는 양수 slot을 요구하며, 1 이상의 명시 slot으로
실패 진단을 보존할 수 있지만 모델 호출은 0회다.

서버의 `selected_problem`은 실제 `resolve_candidate_evidence`를 사용한다.
새 실행에서는 `success_report` 소비 gate를 다시 검사한다. 실패 목적 ref의
진단은 새 성공 결과로 세탁하지 않는다. 원 fit의 실패/holdout/상세 attempt는
이번 진단과 별도이며 후속 성공으로 소급 변경하지 않는다.

일반 J가 저장된 결과를 재사용할 때는 `final_request(..., evaluations=1,
reuse_result=exact_diagnostic_result_reference)`로 명시한다. 비용은 0 모델 호출이다.
`read_jacobian(result, problem)`은 행렬·결합·일관성 gate만 확인하고 evaluator를
부르지 않는다. 현재 원 문제와 다르면 재사용하지 않는다.

## 4. 현재 Plan과 보존 결과 읽기

`numerical.experiment.preview`는 기존 document command의 읽기 전용 분기다.
arguments는 `{}`, 현재 session/generation이 필요하다. source problem과 cost를
반환하며 문서를 바꾸거나 job을 제출하지 않는다. 저장/실행 명령의 receipt와 다르다.

일반 `document_read`, `document_result`, `document_result_reference`는 기존 API다.
새 결과의 `experiment_analysis` 안에 원 문제, 명시 specification/차분 설정,
source_problem_sha256, 일반 J와 실제 attempt가 보존된다. 주 화면에서는 원값,
곡선, 미확인 이유와 판단을 보여 주고 내부 ID/hash는 진단에서만 연다.

Report 캡처는 `validate_report_capture`로 원 evidence 소비 권한과 일반 J를
검증한 뒤 기존 Report owner에 동결한다. 새 owner에서 **이미 저장한 report를 읽을
때에는 모델을 실행하거나 그때의 current candidate로 결과를 대체하지 않는다**.
`experiment_analysis_reporting`은 기존 report payload를 위한 projection이며
또 다른 report store가 아니다.

## 5. FN30 읽기와 계산 환류

`expert_journal_inspection.read_journal(discussion_owner, document_id, original_job_id,
offset=0, limit=64)`는 기존 owner result를 읽는다. 최대 page 256개, next_offset
반환. prompt/text/key는 원 saved journal이며 adopted_utterance는 false다.
유효 replay 후보도 현재 권한/원자료/한도를 통과해야 한다. 읽기로 ANSWERED가 되지 않는다.

명시 재개는 기존 `expert.retry`뿐이다. 이 패킷은 Sol의 partial-reader GUI 또는
재시도 명령 형식을 바꾸지 않는다. `expert_summary(result)`는 새 두 분석 종류에
대해서만 첫 8개 원값/계수 중심 요약을 제공한다. 전체 원결과 해시와 생략 수를 남기고
`reading_scope`에 전체 상세가 comparison/adoption/success report에 필요하다고 명시한다.
기존 Co-STORM formatter 한도와 source permission은 변경하지 않는다.
