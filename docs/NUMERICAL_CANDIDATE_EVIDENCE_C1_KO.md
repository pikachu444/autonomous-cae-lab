# C1 — 선택 후보의 상세근거 보존과 성공판단 gate

요청: **PRO-NUMERICAL-DETAIL-20261015-01-C1**. 대상은 C03/B4.4/FN07-02와 FN07/FN21의 같은 후보 상세 기능이다. 첫 인도의 원 fit/detail_eval 엔진을 재사용한다. 이 문서는 첫 인도의 `frozen-fit-inclusion.v1`을 Data와 합의된 계약으로 설명했던 부분을 바로잡는다.

## 사용자 작업

Numerical에서 피팅 결과의 후보를 선택하고 **선택 후보 상세…**를 연다. 왼쪽 시험 목록에서 시험을 고르면 곡선과 원값·잔차 표가 같은 결과를 보여 준다. 행이나 후보를 바꾸는 동작은 계산하지 않는다. 출력이 없는 시험은 **미보존분 계산**으로 추가 계산한다. 원 피팅의 기록은 그대로 남는다.

상세 창에서 후보와 상세 실행을 선택한 뒤 **성공 결과 → 선택 결과 저장**을 누른다. 계수를 채택하려면 피팅·별도 확인 시험의 필수 출력이 모두 있어야 한다. 계산 완료 여부, 원값·예측·잔차와 단위를 확인하고 계획에 저장한다. 저장에 실패하면 이전 저장본을 유지하며 채택을 진행하지 않는다.

비교 후보와 상세 실행을 고르면 두 결과를 나란히 읽을 수 있다. **선택 시험 비교**는 현재 시험의 두 결과를 저장한 뒤 비교한다. 비교하지 않은 시험까지 합격으로 판정하거나 후보 순위를 자동으로 정하지 않는다.

실패한 계산은 **실패·취소 진단 → 선택 결과 저장**으로 남긴다. 오류 이유와 남은 원출력을 보존하며, 출력이 없으면 없다고 표시한다. 단순히 상세를 저장하지 않은 성공 후보를 실패로 바꾸지 않는다. 실패·취소 기록으로는 성공 결과 비교나 계수 채택을 진행할 수 없다.

**보고서 열기**로 선택 결과를 보고서에 넣는다. 계수와 시험별 원값·예측·잔차·실패 내용을 저장하며, 보고서를 다시 열어 계속 편집할 수 있다. 보고서 창에서 계산 결과를 직접 추가할 때에는 **요약만 넣기**와 **선택한 계산 결과 확인…** 중 하나를 고른다. 요약만 넣은 내용으로는 상세 결과나 계수 채택 여부를 확인할 수 없다. 내부 식별값은 필요할 때 **자료 → 선택 결과 진단…**에서 확인한다.

성공 근거를 보존한 뒤 원 Numerical/RequestPlan 창의 **채택**을 누르면 같은 ref로 서버 preview와 최종 채택을 검증한다. 대화 중 후보·원 job·선택 근거가 바뀌면 취소한다. GUI 버튼 disable에 의존하지 않으며 기존 `DesktopLinks.adopt`, `pde_adopt`, `domain_candidate.adopt`와 직접 `adopted_draft` fit 호출에도 같은 gate가 있다. 일반 수동 Material 편집을 금지하는 기능은 아니다.

## 판단의 범위

| 목적/상태 | 허용 조건과 의미 |
|---|---|
| summary / metadata / 보존 raw 읽기 | 상세가 미보존이어도 허용. job 생성과 성공판단 없음 |
| `READY_TO_PRESERVE` | 입력/출력 검사를 통과해 저장할 준비가 됨. 아직 판단 허가가 아님 |
| `IMMUTABLE_REVISION_VERIFIED` | exact saved revision의 원 입력·job·result·snapshot을 재검증함 |
| 성공 비교 / 성공 보고 | ref의 명시 필수 시험 범위만 성공근거 사용 허용 |
| 채택 | 원 fit에 동결된 모든 fit 및 holdout 시험을 요구. subset ref 불허 |
| 실패 보고 | 실패 기록과 정확한 refs 보존. 실패 시험에 성공/유한 예측을 요구하지 않음 |
| engineering / holdout 합격 | 각각 `NOT_RELEASED`, `NOT_ASSESSED`. 이 모듈은 합격 임계값·공학 자격을 부여하지 않음 |

기본 scope는 동결 실험 전체다. `required_experiments`로 비교/보고 범위를 명시적으로 줄일 수 있지만 빈 범위, 중복, 없는 시험은 거절한다. 각 실험은 원 response, role, unit, scale의 응답 단위, experiment hash를 갖는다. 표본 범위는 새 mask로 바꾸지 않고 원 fit inclusion 그대로다. 관측 품질 mask와 fit mask는 별도로 보존한다. 제외한 원값은 0/예측으로 채우지 않는다. 기존 event 정렬·비발생 penalty도 재작성하지 않는다.

`original_fit_holdout` 및 그 해시는 원 fit 결과의 내용 그대로다. `selected_holdout_refs`는 원 fit 또는 선택 ancestry 안에서 실제로 생산한 job/attempt를 가리킨다. 후속 holdout을 원 fit에 소급 기입하지 않는다. 원 후보가 SUCCEEDED여도 선택 detail가 FAILED/CANCELLED/PARTIAL_FAILURE이면 성공 gate는 닫힌다. 이후 성공한 retry가 있더라도 과거 실패 attempt의 ref와 내용은 그대로다.

## 공개 Python API

`caelab.numerical_candidate_evidence`:

- `candidate_detail_readiness(view, required_experiments=None, purpose='success_judgment')`: 읽기 전용 준비 상태. 그 boolean을 채택 허가로 사용하지 않는다.
- `prepare_candidate_evidence(owner, source, candidate_id, attempt_job_id=None, required_experiments=None, purpose=...)`: 원 owner 결과를 검증하여 snapshot을 준비한다. 계산·저장·job 생성 없음.
- `resolve_candidate_evidence(owner, reference, consumer='read', source=None, candidate_id=None, attempt_job_id=...)`: 저장 개정에서 재검증하는 공통 권한 경계. `comparison/adoption/success_report/failure_report`를 목적대로 명시한다. `attempt_job_id=None`을 넘기면 원 fit 선택과 일치해야 하며, 인자 생략은 ref 자체의 선택을 사용한다.
- `compare_selected_candidate_evidence(owner, left_ref, right_ref, experiment_id)`: 두 immutable ref에 근거한 선택 시험 비교. 다른 원 job/input 또는 범위 밖 시험을 거절한다.
- `candidate_adoption_preview(owner, ref)`, `candidate_report_payload(owner, ref)`: 기존 채택과 보고서 소비자용 결과. 원 callback을 새 evaluator로 대체하지 않는다.

원 읽기 API `read_candidate_detail`과 `compare_candidate_details`는 유지한다. 비교 반환에는 이제 `completion`, `success_judgment_permitted=False`, 양쪽 `readiness`, exact source/input/attempt가 추가된다. 기존 fit `adopted_draft`는 `evidence_owner`와 `detail_evidence` keyword가 필요하다. objective-only 채택의 안전하지 않은 기존 동작은 의도적으로 차단한다. 비-fit 채택 호출 계약은 바꾸지 않는다.

명시 저장 예시(실제 owner와 원 읽기 결과 `view` 사용):

```python
from caelab.numerical_candidate_evidence import CAPTURE, resolve_candidate_evidence

identifier = view['source']['document_id']
document = owner.read(identifier)
receipt = owner.command(identifier, CAPTURE, {
    'source': view['source'],
    'candidate_id': view['candidate']['candidate_id'],
    'attempt_job_id': view['attempt_job_id'],  # None은 원 fit. 최신 attempt를 추측하지 않음.
    'purpose': 'success_judgment',
}, session_id=document['session_id'],
   expected_generation=document['generation'], command_id='CexplicitCapture001')
reference = receipt['reference']
verified = resolve_candidate_evidence(owner, reference, consumer='adoption')
```

`CAPTURE`는 원 계산/자료 owner를 대신 저장하는 coordinator가 아니다. 이미 Numerical에 동결된 입력·결과와 snapshot을 기존 `_save` transaction으로 보존한다. 원 Plan input_revision은 바꾸지 않고 저장 근거 목록의 generation만 진행한다. 저장 재시도는 동일 session/generation/arguments/command_id로 해야 한다. 동일 command_id의 다른 요청은 거절한다. 성공 응답 유실 후 재시도는 저장한 ref를 검증하여 반환한다.

## 기존 service / CLI 연결

새 HTTP route나 controller는 없다. 기존 document-command endpoint가 아래 명령을 전달한다.

```text
numerical.evidence.capture           source, candidate_id, attempt_job_id, purpose, [required_experiments]
numerical.evidence.read              reference, [consumer]
numerical.evidence.compare           left, right, experiment_id
numerical.evidence.adoption_preview  reference
numerical.evidence.adopt             reference, target_document_id, target_kind, target_generation
```

`target_kind`는 `material/pde/domain`이다. adopt는 Workbench에서 기존 대상 owner 채택으로 위임하며 정확한 원 target 및 대상 generation 조건을 유지한다. 실제 GUI/Client도 이 generic command 경로를 사용한다. `.read/.compare/.adoption_preview`는 owner generation 확인 외 쓰기·계산이 없다. 미래 root의 별도 command registry에도 이 dispatch를 그대로 연결해야 하며, GUI enable만 복제하면 안 된다.

CLI는 기존 service에 정확한 JSON 명령을 전달할 뿐 controller나 계산을 시작하지 않는다.

```sh
python -m caelab.numerical_candidate_evidence_cli --service http://127.0.0.1:PORT --request capture.json --output receipt.json
```

`capture.json`은 `document_id, operation, arguments, session_id, expected_generation, command_id`를 모두 갖는 JSON object다. arguments는 위와 같다. UTF-8/BOM을 받으며 응답 유실 시 같은 파일로 재시도한다. 로컬 URL은 전송 경계이고 UI는 PySide6다. `execute_request(client, request)`로 Python에서도 같은 명령과 gate를 사용한다.

## immutable ref와 저장 형식

ref에는 `saved_revision, evidence_id, snapshot_sha256` 외에 원 `document_id/job_id/input_revision/input_sha256/result_sha256`, 원 `candidate_id/candidate_sha256`, 정확한 `attempt_job_id`, ancestry hash, scope hash, purpose가 모두 들어간다. 하나를 바꾸거나 다른 job의 같은 candidate ID로 바꾸면 거절한다. 각 trial ref에는 실제 생성 job/result/attempt, raw/curve/trial hash가 들어가며 없던 raw/result는 `None`이다.

저장 위치는 기존 Numerical owner의 `revisions/<revision>/candidate_evidence/<content-hash>.json`이다. 기존 revision manifest, saved input/job/result refs와 `canonical_hash`를 재사용한다. working JSON이나 메모리 readiness를 성공 근거로 믿지 않는다. 과거 saved revision은 current draft/최신 attempt에 의존하지 않는다. 저장 후 경로를 한글·공백 경로로 옮기고 jobs/current results를 제거해도 원 saved revision만으로 다시 검증된다. 새 프로세스에는 읽기용 owner만 있어도 된다.

snapshot은 64 MiB를 넘으면 완료를 기록하지 않는다. 기존 Report snapshot의 8 MiB 제한도 유지된다. 커다란 근거의 보고 캡처가 그 한도를 넘으면 명시 실패하며 축약 성공으로 바꾸지 않는다. 이 C1은 결과 보존 상한, DB, chunk store, 별도 coordinator를 새로 만들지 않는다.

### 기존 저장기의 수치형 강제 변환 교정

관측/protocol metadata의 혼합 정수·실수 JSON list를 일반 ndarray 최적화로 저장하면 `1`이 `1.0`으로 바뀌어 원입력 hash가 깨질 수 있었다. `evaluation.py`의 최소 hunk는 **`caelab.frozen-fit-input.v1`과 `caelab.candidate-detail.v1` capsule 내부의 Python list만** 원 JSON 수치형으로 보존한다. 실제 ndarray는 기존 .npy 저장을 사용하고 일반 응답/결과 저장 형식은 그대로다. 큰 정수/boolean과 혼합 deformation matrix를 회귀 검사했다. 이미 잘못 변환된 과거 파일의 해시를 몰래 재작성하거나 복구 성공으로 인정하지 않는다.

## Data 후속 통합 경계 — 합의된 compiler 계약 아님

`caelab.frozen-fit-inclusion.v1`은 첫 인도에서 제안한 **Numerical-local legacy packet**이다. Data의 최종 공개 API/packet과 합의·통합 완료된 shared 계약이 아니다. 기존 observation/protocol/source hash 소비는 유지하지만, 파생 표본의 quality/gap/Plan compiler나 related-save coordinator를 작성하지 않았다.

새 전용 `caelab.numerical_fit_lineage`는 전달 envelope의 구조만 검증한다. `_OBSERVATIONS.additionalProperties=False`를 완전히 풀지 않고 다음 typed fields를 추가한다.

```text
source_rows: integer[]                              # 기존 의미 유지. 파생 ID로 치환 금지
sample_ids: unique string[]                         # 관측 순서와 같은 별도 ID
contributors: [{sample_id, raw_contributors, operation_refs, extensions?}]
raw_contributors: [{source_sha256, source_column_identity, source_row: integer,
                    weight: finite number, extensions?}]
operation_refs: [{operation_id, sha256, document_id?, saved_revision?}]
operation_metadata: {schema: nonempty string, payload: object}
extensions: {namespace: {schema: nonempty string, payload: object}}
experiment.extensions: 위와 같은 namespaced envelope
```

이는 Data의 최종 field명에 대한 약속이 아니다. 최종 packet 모양이 다르면 namespaced `extensions.<namespace>.payload`에 그 JSON을 손실 없이 보관하고 root가 실제 API에 맞는 adapter를 붙인다. 각 단계 quality/gap/Plan inclusion·role·weight, observation/driver target grid, 실제 raw contributor weights와 operation refs를 변형하지 않고 담을 수 있다. 임의 flat fields, 잘못된 순서/길이, string source_rows, 비유한 weights는 거절한다. 검증을 명목으로 누락 contributor/weights나 보간 출력을 생성하지 않는다.

`consume_data_extensions(experiments, validator)`가 최종 Data consumer를 root가 주입할 경계다. detached packet을 받아 검사하고 `None`을 반환하거나 예외를 발생시키는 실제 consumer만 붙인다. 이 함수는 packet을 바꾸거나 해시를 새로 매겨 원입력 의미를 교체하지 않는다. 현재 제출·readiness는 이 아직 없는 consumer를 자동 호출하지 않는다.

**파생 표본 독립성은 항상 `NOT_VERIFIED`다.** 같은 raw contributor를 공유하지만 integer source_rows가 다른 train/holdout 사례를 실제 전용 테스트에 넣었으며, 보존만 하고 독립성이 입증됐다고 표시하지 않는다. legacy `require_independent_rows`로 이 누출을 해결했다고 주장하지 않는다. root는 Data 최종 packet 수령 후 raw contributor independence, 실제 동일 target grid, 단계별 유효 mask admission을 Data-owned compiler에서 검증해야 한다. 성공근거 보존은 이 compiler 검증이나 holdout 합격을 대신하지 않는다.

## 적용과 검증

C1의 `integration.patch`는 **원 두 ZIP + 앞선 공식 인도 전용 파일/원 integration.patch가 이미 적용된 상태**를 기준으로 하는 증분 패치다. 첫 patch를 C1 patch로 교체하면 안 된다. 전용 파일은 이번 파일로 갱신하고, 공유 파일은 패치 hunk만 통합한다. `fccda9b/f2c59cc/37e202e` 이후 root의 실제 파일은 이 대화에 없으므로 그 버전에 자동 적용됐다고 주장하지 않는다.

```sh
git -c core.whitespace=cr-at-eol apply --check integration.patch
git -c core.whitespace=cr-at-eol apply integration.patch
python -m pytest -q tests/test_numerical_candidate_evidence_c1.py
python -m pytest -q tests/test_numerical_candidate_evidence_consumers_c1.py tests/test_numerical_fit_lineage_c1.py
python -m pytest -q tests/test_numerical_candidate_evidence_felupe_c1.py tests/test_numerical_candidate_evidence_ui_c1.py -rs
```

검사용 `tools/verify_candidate_evidence_c1_delivery.py`는 빈 폴더에 첨부 원 ZIP 둘, 회수 원 인도, C1 전용 파일과 공유 패치를 순서대로 복원하여 baseline/결과 파일 해시 및 문법을 대조한다. 사용 중인 workspace에는 적용하지 않는다. 실제 실행 집계/명령/환경 차이는 `DELIVERY.md`와 `evidence/`가 기준이다. Linux 합성 fixture 검사와 실제 FELUPE·Windows Qt는 별도이며, 이번 환경에서 없는 runtime은 NOT_RUN으로 둔다.

FN08/18~24 전체, FN02 관련 저장/Plan widget, Data compiler, material mixed-control/identification, 다른 mesh/time mapping, 사용자 law FE pair는 이번 교정의 완료 범위가 아니다. 기존 수치/UQ/ODE/weak/RBF/Sobol/epsilon/DE/동일 mesh 전송은 재작성하지 않았다.
