# CAE Research Team — 실제 조사·상호검토·계산 환류 최종 상세 설계

요청 ID: **PRO-CAE-RESEARCH-TEAM-20261016-02**
설계일: 2026-10-16
문서 판: **R2 / 앞선 PRO-CAE-RESEARCH-TEAM-20261016-01.md 전체 대체본**
상태: **구현 계약 확정. 제품 구현·수용시험·공학 승인 완료 보고가 아니다.**

## 0. 결정 요약과 근거의 경계

기존 `DiscussionDocuments(X)`를 토론의 유일한 owner로 유지한다. 역할별 실제 조사·도구 사용은 `ExpertRuntime`, 진행·논점 지도·보고서 초안은 pinned Co-STORM, 계산·형상 변경은 기존 Numerical/Simulation/FreeCAD 경로가 맡는다. 기존 OpenScience 구독 호스트를 재사용한다. 별도 토론 앱, ACL, workflow 엔진, 에이전트 프레임워크, 서버, 저장소, solver를 만들지 않는다.

이 교체본은 다음 다섯 결정을 고정한다.

| 결정 | 확정 계약 | 상세 절 |
|---|---|---|
| 유한 예산 일정 | 기존 `_Budget`의 실제 예약 함수에 trusted allocation을 연결한다. 도구 조사 2 steps, 전달된 근거로 하는 질문 1 step, 근거 답변 2 steps를 기본 ticket으로 계획한다. 초기 조사 barrier를 먼저 만족시키며, 완료 과제는 다음 action에서 다시 호출하지 않는다. | §4 |
| 응답 전체의 생성 의존성 | runtime이 실제 공급한 prompt·자동 snippets·history·도구 반환·자문·정확 결과의 전이적 의존성을 응답 전체에 붙인다. 모델 인용 목록으로 축소하지 않는다. | §3, §5.3 |
| 실제 도구 dispatch 강제 | 호출별 trusted binding으로 exact result/selector, 공동 public search journal, 명시 numerical analysis scope를 집행한다. `_ask` 복제나 전역 callback 교체는 없다. | §5.2, §9, §10 |
| 역할 완료와 지도 반영 분리 | 실제 `CoStormRunner.step`에 `DeferredKnowledgeBase`를 장착한다. step의 삽입 요청은 pending checkpoint만 만든다. 실제 KB 삽입은 승인 snapshot의 임시 사본에서 수행하고 성공한 사본만 공개한다. | §8 |
| 최신 공개검색 시작 경로 | 선택 문헌 필수 조건을 일반 Co-STORM에 다시 넣지 않는다. 현재 public topic-only와 verified results-only 시작을 보호하고, 자료 없는 문제정의도 유지한다. | §8.5 |

같은 기반모델도 작업·상태·자료·도구·응답 귀속이 분리되면 별도 에이전트로 구성할 수 있다. 그러나 모델 다수의 일치, 도구 성공, JSON 검증, solver 성공은 각각 공학 적합성 또는 release 승인이 아니다. 연구팀의 산출물은 근거가 연결된 가설·질문·반론·수정, 미해결 항목, 다음 시험·계산과 실제 결과에 대한 후속 판단이다.

### 0.1 이번 근거와 현재 기준

실제로 읽은 입력은 `correction-request.md` 전체, Astra의 `REVIEW.md` 전체, 이전 전체 설계 MD이다. 원문별 확인 범위와 식별 정보는 §15에 기록한다. 아래 현재 소스 사실은 **root/Astra가 직접 읽어 첨부에 확정해 준 사실**이다. 이번 설계 수정에서 최신 저장소 전체 또는 사용자의 로컬 WIP를 다시 읽었다는 뜻이 아니다.

- 요청 기준 main: `68c8b53b3dca98bb6ca213bb991fb7594bd19f19`.
- fixture pin: `3e48bf6138f495299f45b1af254bfb4aaff307b8`.
- Co-STORM vendor: `fb951af7744dab086e34962e9bc6fe878e145f83`.
- 보호할 통합 성과: 공개검색 `8dddcb2`, 충격 B `e416dbc`, 피로 C `d841640`, Post field 비교 `68c8b53` 및 첨부가 설명한 로컬 Study/Expert/Report portable와 Numerical 확장.
- Astra의 읽기 기준은 `d841640b8d74973005fb706e4b83ed22108689d7` 및 당시 로컬 portable/Numerical 변경이다. 그것을 요청 기준 main과 혼동하지 않는다.
- 이전 `ade0ca6` 구간 조회와 `eaa33cf6` portable 인도는 과거 근거다. 현재 본문을 덮어쓸 baseline으로 사용하지 않는다.

Astra 판정은 “방향 PASS, 네 실행 계약 보완 후 채택”이다. 이 문서는 그 보완과 최신 공개검색 호환성을 한 번에 결정한다. 기존 사용자 예산의 자동 증대, 새 과금·API키·계정·크레딧, 새 설치·상주 서버·WSL 필수는 없다. 일반 CAE 기능에 AI/MCP를 필수로 만들지 않는다.

### 0.2 확인 사실과 새 설계의 구별

현재 Discussion 기본 예산은 `model_calls=4, tool_calls=8, consultations=0, seconds=120`이고 runtime의 모델 상한 8과 다르다. 기존 예약 함수는 실제 청구량 대신 host의 허용 steps를 보수적으로 선예약한다. 이번 설계가 미사용 추정분 환불을 추가하지 않는다.[REQ1][REV1]

현재 `_ask`의 자동 source 주입·세션 history·도구/자문 반환, job ID 위주의 결과 범위, 직접 `numerical.analyze` callback과 upstream의 무조건 KB 삽입은 첨부의 코드 관찰에 따른다.[REQ2][REQ3][REQ4] 아래의 새 자료형·함수명·상태는 **작성할 인터페이스**다. 이미 구현됐다고 표현하지 않는다.

이번에는 provider·solver·Windows/Qt 실행, 원격 게시, 새 제품 테스트를 수행하지 않는다. 문서 파일 생성·UTF-8 재읽기·구조 검사는 설계 산출물 확인일 뿐 제품 수용이 아니다. 이전 문서의 외부 참고자료는 과거 참고로 유지하며 최신 상태를 재확인했다고 주장하지 않는다.

### 0.3 호환성 식별

새 실행은 `draft.context.research_team.version=2`, `protocol_request.variant='cae_research_team_v2'`, 반환 `costorm.team.version=2`로 식별한다. 기존 draft 최상위 key와 `discussion_mode='costorm'`는 유지한다. 이 version은 이번 실행 계약의 판별자이지 새 문서 owner/schema framework가 아니다.

`research_team`이 없는 기존 sequential/Co-STORM은 현행 경로 그대로다. 이전 설계의 v1 초안·로컬 작성물이 있으면 읽기/보존하고, **사용자의 명시 다음 단계 작성**에서 v2 초안을 만든다. v1의 원 실행·session·hash·READY 상태를 v2 실행 권한으로 자동 승격하지 않는다. provenance가 없는 옛 응답은 `DEPENDENCY_UNVERIFIED`이며 새 모델/shared KB 입력으로 자동 편입하지 않는다. 기존 허용된 로컬 원문 읽기까지 소급 삭제하지 않는다.

## 1. 선택한 전체 구조

```text
사용자: 주제·질문·문헌·시험자료·실제 결과·현재 허용 범위
  │
  ▼
기존 ExpertWindow / StudyWindow — native Qt
  │  구성 검토 / 명시 연구 시작 / 개입 / 중단 / 저장
  ▼
DiscussionDocuments(X): draft + append-only turns/rounds + 기존 command receipt/CAS
  │
  ├─ research-team 모드용 작은 owner helper
  │     단계/담당 과제/질문 대상/호출 상한/현재 권한을 동결
  │
  └─ 기존 JobManager의 experts.ask 작업 1개
        │
        ├─ Co-STORM 진행 정책 어댑터
        │     다음 실제 담당자 선택 / 미사용 근거 질문 / 지도·보고서
        │
        ├─ ExpertRuntime의 역할별 실행
        │     역할별 session·자료·도구·model / 공통 예산·취소 경계
        │       ├─ KnowledgeStore.search/source
        │       ├─ Literature.search/read
        │       ├─ results.read / calculations.inputs / numerical.analyze
        │       └─ calculations.plan / 제한된 experts.consult
        │
        └─ 검증된 발언·근거·도구기록·계산제안 → X에 보존
               │
               ├─ 명시 채택 → 기존 StudyDocuments(S)
               ├─ 명시 계획 열기 → 기존 Numerical Plan(N)
               │     사용자 입력검토·기존 실행허가 → 기존 JobManager/solver
               │     실제 결과 저장·선택 → 같은 연구의 다음 단계
               └─ 명시 보고서 편집 → 기존 ReportDocuments
```

Workbench GUI를 반드시 열게 하지 않는다. 기존 독립 Qt 앱과 common Workbench service/client를 쓴다. 모델 미설정·로그인 만료·네트워크 차단 상태에서도 문헌/과거 발언/계획/결과 읽기와 편집·Undo·저장은 가능해야 한다. 일반 CAE 작업은 AI 또는 MCP를 요구하지 않는다. 기존 OpenScience 호출에 붙는 수명 제한 localhost bridge를 재사용할 뿐, 새 상주 서버나 웹 화면은 만들지 않는다.

역할 완료와 map pending은 별도 기록이며 실제 step의 KB 삽입 요청은 전용 proxy를 거친다. 생성 입력 의존성·exact 도구 범위와 단일 예약 예산의 실제 계약은 §3–5/§8–10이 우선한다.

## 2. 연구팀 구성과 실제 전문성의 계약

### 2.1 역할은 등록된 수행 능력의 조합이다

새 예제 정의 파일 `examples/cae_research_experts.json`을 추가한다. 기존 `examples/workbench_experts.json` 및 사용자의 custom registry는 덮어쓰지 않는다. 새 정의는 기존 registry 로딩/연결 화면에서 명시 반입하며 provider·credential·자동 model 선택을 포함하지 않는다.

기존 최대 8개 participant 제한을 유지한다. 아래 역할을 매번 전부 소집하지 않는다. 진행자와 실제 쟁점이 있는 담당자를 선택한다. assignment.mode는 coordinator 또는 investigator로 명시하며 coordinator는 최대 1명이다. coordinator가 없는 작은 연구는 승인된 첫 참가자가 정책 역할을 맡고, 별도 진행자 모델 호출을 숨겨 추가하지 않는다. 공학 결론을 내는 연구에는 반론 역할을 포함한다. 모델은 모두 현재 허용된 같은 모델일 수 있다.

| 등록 역할 | 맡는 일 / 제출해야 하는 것 | 기본 도구와 자료 범위 | 대신하면 안 되는 일 |
|---|---|---|---|
| `cae.coordinator` 진행 | 쟁점 분리, 질문 대상 선택, 불일치·미해결 유지, 다음 단계 정리 | 공유가 허용된 발언/근거; 필요한 공식자료 읽기 | 다수결로 승인, 타 역할 자료 전체 열람, 자원 승인 |
| `cae.literature` 문헌 | 실제 읽은 문헌의 범위·조건·상반된 연구·미읽기 보고 | knowledge.search/source; 허용 시 literature.search/read | 논문 제목/초록으로 수치·설계 적합성을 확정 |
| `cae.structures` 해석 | 요소/재료/접촉/경계·하중·결과 정의·수렴 검토 | solver/FreeCAD 자료, 선택 모델/결과, calculations.inputs/plan, results.read | 새 solver 구현, 임의 shell 실행, 미계산 결과 생성 |
| `cae.materials` 재료 | 재료법칙·시험 측도·방향/속도/온도·동정 가능성과 근거 | 선택 재료/시험 문서, 측도에 맞는 결과, plan | 논문 상수의 실제 부품 자동 적용, holdout로 재동정 |
| `cae.numerical` 수치 | 민감도/식별성/DOE·수치오차 검토와 판별 계획 | 실제 N 결과, numerical.analyze, calculations.inputs/plan | 계산 실행 횟수 또는 예산 증대 승인 |
| `cae.testing` 시험 | 계측량/조건/반복성/치구 영향·다음 시험 | 사용자 선택 시험기록·공개 시험 방법 | 가상 결과를 실험값으로 기입, 유료 표준 전문을 읽었다고 주장 |
| `cae.design` 설계·제작 | 형상/조립/공차/접근성·제작조건과 native 변경안 | 선택 FreeCAD 모델·도면·제작기록과 plan | 현재 CAD에 자동 Apply, 강도 검토만으로 제작 승인 |
| `cae.challenge` 반론 | 주장의 반례·숨은 가정·대안 가설·판별 조건 | 해당 주장의 공유 근거, 필요할 때 허용 자료 직접 확인 | 내용 없는 의무 반대, 새 증거 없는 반복 반박 |

실제 allowlist는 표의 설명이 아니라 현재 registry ∩ 이번 역할에 허용한 도구 ∩ 실행 호스트 capability다. 새 profile의 공통 collection은 기존 KnowledgeStore의 `cae-public`(명시 반입한 공개자료)과 `project-current`를 사용하고, 역할별 추가 collection은 현재 등록 설정에 한한다. 문서의 분야 태그와 읽기 권한을 같은 것으로 취급하지 않는다. 공유 검토할 공개 solver/재료 문서를 분야가 다르다는 이유만으로 막지 않되, 기존 materials/testing 자료의 collection을 몰래 변경하거나 복제하지 않는다. 선택 source와 전송 승인은 여전히 문헌별로 검토한다. 실행 도구 `calculations.submit/numerical.doe/fit/optimize`는 기본 연구 역할에서 활성화하지 않는다. 사용자가 기존 실행 범위를 명시 허용한 경우에만 기존 경계로 노출한다. 처음에는 계획을 만들고 기존 편집기에서 실행하는 경로가 기본이다.

### 2.2 주제로부터 팀을 구성하는 방법

초기 구성은 모델 없이도 완료한다. `불량 원인 / 설계 검토 / 시험·재료 / 자유 연구` 유형과 선택한 문서·결과 종류로 후보를 제안한다. 예를 들어 변형 원인에는 structures/testing/challenge를 기본 후보로 놓고, 재료 불확실성이 있으면 materials, 조건 비교가 있으면 numerical, 외부 연구가 필요하면 literature를 추가한다. 형상·제작 검토에는 design을 추가한다.

선택된 각 역할은 이름 밑에 **“이번에 답할 질문”, “검토할 자료”, “쓸 도구”, “답할 수 없는 부분”**을 가진다. 사용자가 팀 구성을 검토하는 화면에서 수정한다. 모델을 써서 담당 범위를 제안하는 기능은 별도의 명시 동작이고, 그 결과는 등록 역할에 대한 제안일 뿐 권한을 새로 만들지 않는다. 등록되지 않은 전문분야가 필요하면 “현재 팀으로 미충족” 과제로 남긴다.

investigator의 최초 조사에서는 공통 문제정의와 자기 허용자료만 받는다. §4.2의 barrier가 열릴 때까지 다른 역할의 결론·그 결론을 읽은 진행자의 요약·공동 KB를 prompt에 넣지 않는다. 초기 조사 후 현재 공유 가능한 응답 전체의 의존성을 검증하고 대상 질문/반론을 연결한다. 이는 입력 분리 설계이지 통계적 독립성의 증명이 아니다.

### 2.3 전문성이 실제로 생기는 조건

각 역할에는 짧은 분야별 절차를 둔다. 예컨대 structures는 “해석 종료 상태 → 결과 위치/성분/측도 → 하중·반력/에너지 → 요소·접촉·메시 → 실험과 비교가능성”을 확인한다. materials는 측도·단위·시험조건·교정범위·독립 검증을 확인한다. 이 절차는 확인할 항목이지 정답이나 자동 승인 규칙이 아니다.

검증은 역할의 문체가 아니라 실제 과제로 한다. 틀린 단위, 잘못된 결과 성분, 초록만 있는 논문, 미수렴 해석, 재료조건 불일치, 반론 후 수정이 필요한 공개 사례를 사용한다. 결과를 읽지 않은 담당자는 “결과 검토 완료”로 표시하지 않는다. 모델 다수의 일치·정형 JSON 통과·도구 성공은 공학 자격이 아니다.

팀 검토 화면은 기존 기본4와 runtime 상한8을 구별해 표시한다. 3 investigator의 조사는 기본4에서 여러 명시 action으로 나뉘며, 남은 정확한 과제를 보여 준다. 역할 수 때문에 예산을 자동 늘리지 않는다. 모델 없이 준비할 팀 구성/자료 선택은 모델 예산을 소비하지 않는다.

## 3. 기존 owner에 추가할 자료 계약

이 절의 객체는 기존 X owner의 dict/검증기와 bounded assets를 사용한다. callable·lock·현재 권한은 직렬화하지 않는다. 값으로 저장한 source/role 설정은 provenance 또는 허용 범위를 더 좁히는 선택이지 독립적인 권한 증서가 아니다.

### 3.1 작성 영역 — `draft.context.research_team`

| 필드 | 형식 / 의미 |
|---|---|
| `version` | 정수 2 |
| `phase_id`, `parent_phase_id` | owner가 발급하는 현재/이전 단계 ID. 새 단계 작성은 `phase_id=null`로 요청하고 owner가 명시 update 때 배정 |
| `objective`, `deliverable` | 비어 있지 않은 질문·필요 산출물. 결론을 미리 지정하지 않음 |
| `assignments` | 아래 `Assignment[]`, 1..8개 등록 역할, 중복 actor 금지 |
| `shared_evidence` | 기존 exact 문헌/결과 참조의 공유 후보 목록. 현재 권한을 대체하지 않음 |
| `carry_forward_turn_ids` | 다음 단계에 명시 선택한 원 발언 ID. 전체 생성 의존성 재검사 |
| `requested_next` | null 또는 `{expert_id, task_id, target_turn_id, target_claim_id}`. null target은 허용하되 지정 대상은 실제 X 기록이어야 함 |
| `turn_limit` | 이번 action의 신규 역할 발언 상한 1..8. 기존 model/tool/deadline이 우선 |
| `stop_when` | 기존 설계의 종료 이유 목록. 승인이나 자동 실행 조건으로 쓰지 않음 |

`Assignment`의 필드는 `expert_id`, `mode=investigator|coordinator`, `question`, `checks[]`, `tools[]`, `source_refs[]`, `result_refs[]`이다. `result_refs`의 각 항목은 §9.2의 `ResultSelection` wrapper이다. 분야별 자료 태그는 권한과 별개다. model·tools·consultations·seconds의 사용자 한도는 **기존 `draft.budget` 하나**만 사용한다. 분석 허가도 기존 `context.calculation_scope`의 선택적 `analysis` 하위 범위로 작성한다(§9.3).

### 3.2 보존 상태 — `discussion.research_team`

| 기록 | 필수 값과 의미 |
|---|---|
| `PhaseRecord` | `id,parent_id,frozen_draft_ref,assignments,initial_task_ids,initial_barrier,task_ids,shared_turn_ids,current_map_revision,review_status` |
| `TaskRecord` | `id,phase_id,actor_id,kind,priority,depends_on,target_turn_id,target_claim_id,question_ref,input_snapshot_ref,status,completed_response_id,continuation` |
| `ActionRecord` | `id,phase_id,origin='local'\|'archived_origin',kind,command_id,job_id,prepared_arguments_digest,allocation_plan,task_ids,checkpoint_revision,search_ledger_id` |
| `AttemptRecord` | `id,action_id,job_id,command_id,budget_limit,reservations,observed_tool_calls,observed_host_invocations,started_at,terminal_state`; 명시 retry는 새 attempt이며 같은 command의 응답 재확인은 새 attempt가 아님 |
| `RoleResponse` | `id,task_id,actor_id,phase_id,raw_response_ref,validation,input_manifest_ids,dependency_ids,read_receipt_ids,proposal_refs,local_status,shared_projection_id` |
| `SharedProjection` | `id,response_id,body_ref,dependency_ids,recipient_set,validation_record,current_access_status`; 원 응답을 요약해 의존성을 줄이지 않음 |
| `MapPending` | §8.2의 삽입 대상. 역할 응답 완료와 독립 |
| `MapCheckpoint` | `id,previous_id,base_revision,applied_pending_ids,kb_asset_ref,dependency_ids,citation_map,created_by_attempt` |

상기 영문 key는 개발 계약이다. 화면은 한국어 라벨을 사용한다.

`action_id`는 명시 start/advance/report가 만드는 논리 action을 가리킨다. `expert.retry`는 원 action과 미완료 항목을 유지하면서 새 command/job/attempt 및 새로 명시한 기존 예산을 갖는다. 성공 search의 순위와 해당 action의 2-query 상한은 retry로 초기화하지 않는다. 다음 일반 advance는 새 action이지만 이미 완료한 task를 다시 실행할 권한은 아니다.

`task_id`와 완료 응답은 action을 넘어 같은 phase에 남는다. 초기 독립조사와 후속 질문·답변은 다른 task다. response/claim/task ID는 owner가 발급한다. Co-STORM topic path/hash는 표시용이며 영속 claim ID로 쓰지 않는다.

### 3.3 역할 응답 — 기존 envelope + `research_reply`

기존 `answer, assumptions, sources, proposed_actions, tool_events`를 유지한다. `research_reply`에는 `kind`, `claims[]`, `questions[]`, `revisions[]`, `unknowns[]`가 들어간다.

- `kind`: observation/hypothesis/question/challenge/revision/plan/synthesis.
- claim: `text`, `basis=observed|inferred|hypothesized`, `conditions[]`, 모델의 표시용 `source_refs[]`, `missing_evidence[]`.
- question: 승인된 수신 역할, 실제 target claim/turn, 질문, 판단을 구별할 관측.
- revision: 이전 claim, `keep|revise|withdraw|undetermined`, 이유, 근거. 원 claim 삭제/덮어쓰기 금지.
- unknown: 부족한 입력, 판단을 막는지, 다음 관측 또는 실제 `proposed_actions`와의 관계.

`answer_sections`는 새 모드의 prompt/검증에 실제 적용한다. 반환 형식이 틀려도 원 응답과 도구 결과를 보존한다. 형식 교정은 §4의 공용 서비스 몫이 있을 때만 최대 1회, 도구 없는 별도 1-step 호출로 한다. 원 입력 의존성을 모두 계승한다. 교정으로 원문·관측·계산을 만들어내지 않는다. 일반/옛 Expert 답변에 이 형식을 소급 강제하지 않는다.

`VALID`는 구조·실존 인용 연결이 맞다는 뜻이지 공학적 진실 판정이 아니다. 가설/미확인은 자료가 없다는 이유만으로 삭제하지 않는다. 다만 근거 없는 가설을 실제 관측으로 표시하지 않는다.

### 3.4 `InputDependency`와 `ModelInputManifest`

권한 판정의 단위는 모델이 적은 `source_refs`가 아니라 runtime이 만든 **생성 입력 의존성 집합**이다.

`InputDependency`는 `{id, kind, exact_ref, selector, content_digest, parent_ids, introduced_by}`로 고정한다. `kind`는 `knowledge`, `literature`, `result`, `authored`, `role_definition`, `response`, `analysis`, `tool_output`이다. 해당 종류에서 쓰지 않는 selector는 null이다. `exact_ref`는 기존 종류별 참조를 유지하고, 원 참조 내부에 새로운 권한 필드를 넣지 않는다. `introduced_by`는 prompt/auto_snippet/history/forwarded_turn/tool_return/consultation/map_base 중 하나다.

`ModelInputManifest`는 `{id,owner_id,phase_id,task_id,actor_id,attempt_id,host_invocation_id,mode,payload_digest,payload_bytes,dependency_ids,coverage,status}`이다. `mode`는 `initial|tool_followup|repair|map|report|public_clean`이다. `coverage`는 `COMPLETE_SUPPLIED_INPUT` 또는 `UNVERIFIED`다. 숨은 모델 사고과정·계정/호스트 credential을 수집하지 않는다.

`COMPLETE_SUPPLIED_INPUT`은 **제품이 실제 공급한 입력의 추적이 완전**하다는 뜻이다. Haystack은 각 모델 호출 메시지에서, OpenScience는 실제 넘긴 prompt와 해당 host invocation에 반환한 모든 scoped tool 응답의 누적 합집합에서 기록한다. CLI 내부의 관찰 불가능한 세부 모델 turn이나 청구량을 안다고 표시하지 않는다. 제품 밖 도구·보이지 않는 파일이 섞이는 실행은 이 coverage로 통과시키지 않는다.

역할 응답의 `dependency_ids`는 그 응답을 만든 모든 manifest의 전이적 합집합이다. raw response, 질문, 가설, 수정 이유, 제안 Plan 전체가 이 집합에 결속된다. 한 응답에서 특정 문장만 골라도 이 의존성을 줄이지 않는다. 모델이 이 필드들을 출력하면 무시하고 runtime 기록만 사용한다.

### 3.5 실제 읽기 receipt와 표시 상태

`ReadReceipt`는 `{id,kind,request_digest,source_ref,requested_selector,returned_selector,read_level,returned_digest,returned_bytes,payload_ref,dependency_ids,status,limitations}`이다. result에는 §9.2의 exact 검증 receipt가 연결된다. 표시용 원 `run_id/response_selection` citation은 호환성을 위해 남기지만 exact 선택의 권한 증거로 쓰지 않는다.

검색 후보 / 서지만 확인 / 초록 읽음 / 선택 본문 읽음 / 추출 불완전 / 접근 불가 / 현재 권한 거부 / 실제 결과 읽음 / 부분·실패 결과를 구별한다. 도구 성공과 읽은 범위, 읽은 범위와 해당 업무의 적용성, 적용성과 공학 승인은 각각 다른 상태다.

### 3.6 상한과 원본 보존

기존 payload/asset/portable 용량 상한을 우선한다. 큰 반환값을 모델 prompt에서 생략하면 생략 사실과 실제 전송 범위를 기록한다. 원 tool 반환은 허용된 bounded asset으로 보존하거나 기존 retained reference를 사용한다. 일부 생략을 이유로 생성 의존성은 줄이지 않는다. 큰 원 결과 전체를 자동 전송하거나 새 원자료 store를 만들지 않는다.

`source_closure`는 이제 `RoleResponse.dependency_ids`, manifest, read receipt, pending/committed map, report 및 원 authored/Plan/result 참조의 **선언된 closure**를 수집한다. 모델 `claims[].source_refs`만 훑는 이전 규정은 폐기한다. closure 수집 자체는 권한 승인 또는 fetch가 아니다.

## 4. 실행과 실제 예산으로 끝나는 역할 일정

### 4.1 실행 owner와 정상 시작

기존 `expert.ask/advance/report/retry` → `DiscussionDocuments._submit_next` → `experts.ask` JobManager 작업을 유지한다. 하나의 action/attempt에는 상위 job 하나와 모델 동시 실행 하나만 둔다. 내부 역할이 자식 job을 제출하고 그 queue를 기다리지 않는다. 기존 worker 안에서 `_run_approved_role` → `_ask`를 호출한다.

owner가 검증한 `protocol_request.variant='cae_research_team_v2'`만 팀 경로에 들어간다. `owner_step/_TRUSTED`와 `discussion_costorm.authorize`를 그대로 거친다. 모델 context에 variant 또는 binding과 비슷한 JSON을 써도 권한을 얻지 못한다.

연구 시작은 기존 예산 안의 유한한 역할 일정을 승인한다. poll/read/save/Undo는 표시 갱신과 검증된 **현지 완료 기록 수집**만 하며, 다음 역할·새 action·새 검색을 승인하지 않는다.

### 4.2 초기 독립조사의 barrier

phase 시작 때 mode=investigator인 역할별 `INITIAL_RESEARCH` task를 owner가 순서대로 발급한다. coordinator는 정책 수행자이며 초기 독립조사를 자동 배정하지 않는다. 초기 입력은 공통 authored 문제정의, 역할 정의·담당 질문, 자기 허용 자료·결과만이다. **같은 phase 다른 역할의 답변, 주장 목록, 지도, 보고서, 그 답변을 읽은 진행자의 요약을 초기 role context에 넣지 않는다.** 실제 step이 공동 history/KB를 agent에 인자로 주어도 초기 agent는 그 객체를 prompt로 전달하지 않는다.

모든 초기 task가 `COMPLETED` 또는 사용자가 명시한 `ACKNOWLEDGED_UNRESOLVED`가 될 때까지 초기 barrier는 닫혀 있다. 예산 부족으로 아직 시작하지 못한 역할은 unresolved로 자동 바꾸지 않는다. 형식 실패·권한 부족도 완료로 위장하지 않는다.

barrier가 열린 뒤에만 대상 질문·반론과 답변을 실행한다. 우선순위는 다음과 같다.

1. pause/취소/새 사용자 개입 확인. 개입이 있으면 이번 고정 입력의 다음 역할 시작을 멈춘다.
2. barrier가 닫혔으면 남은 초기 조사 또는 그 조사 응답의 미완료 final/repair.
3. barrier가 열렸으면 명시 사용자 대상 질문, 기존 미답 질문의 답변, 아직 수행하지 않은 최초 교차검토 질문.
4. 근거 부족·불일치에 대한 후속 검토와 다음 시험/계산 제안.
5. 사용자가 승인한 추가 탐색·종합. 정해진 역할·과제·budget 안에서만 수행한다.

초기 조사 도중 사용자가 자료·역할·문제정의를 바꾸면 같은 X의 다음 phase로 처리한다. 이전 완료 조사는 지우지 않고 이전 조건의 조사로 남긴다. 같은 입력의 반복 읽기/advance로 최초 조사를 재호출하지 않는다. 중요 주장이 모두 비공유이면 반론할 내용을 만들어내지 않고 `공유 가능한 근거/발언 필요`로 멈춘다.

### 4.3 단일 예산과 ticket 비용

유효 한도는 기존 runtime이 허용하는 값과 명시한 `draft.budget`의 작은 값이다. **Discussion 기본 4/8/0/120과 runtime 모델 상한 8을 구별한다.** role별 전체 `_Budget` 재생성, 잔여 추정 청구량 환불, 사용자 값 자동 증가를 금지한다.

각 action 시작에 `AllocationPlan`을 만들고 checkpoint한다. 실제 모델 호출 전에 task별 입력·대상·의존성을 다시 동결하고 현재 권한을 확인한다. 동적으로 결정되는 교차검토 질문의 target은 초기 조사 완료 후 실제 claim 중에서 선택해 task 입력에 기록한다. 이 선택은 부모의 원 `prepared_arguments`를 바꾸지 않는, 승인된 과제 범위 안의 실행 기록이다.

| ticket | 모델 steps 배정 | 도구/자문 | 시작에 필요한 최소 조건 |
|---|---:|---|---|
| `EVIDENCE` | 2 | 기본 도구 반환 1회, consult 0 | 모델 2·도구 1 이상과 해당 도구 scope. 한 번의 도구 사용 후 최종 응답 여유를 확보 |
| `QUESTION` | 1 | 도구 0, consult 0 | barrier 개방, 현재 공유 가능한 실제 target, 모델 1 |
| `ANSWER` | 2 | 기본 도구 반환 1회, consult 0 | 대상 질문/근거가 허용됨, 모델 2·도구 1 |
| `FINALIZE` | 1 | 도구 0 | 자기 task의 실제 보존 도구 반환·입력이 있고 최종 응답만 미완료 |
| `REPAIR` | 1 | 도구 0 | raw 응답 존재, 구조 검증 실패, 이 응답의 자동 repair를 아직 사용하지 않음 |
| `MAP_SERVICE` | 1 이상 | provider 도구 0 | 공유 projection·pending이 있고 현재 원자료/기존 KB 전체 의존성이 허용됨 |
| `REPORT_SERVICE` | 1 이상 | provider 도구 0 | 명시 보고서 action, 현재 허용된 지도·발언·근거 |

EVIDENCE/ANSWER의 2는 **허용 가능한 한 도구 round + 최종 답변을 위한 host 상한**이다. 실제 모델이 반드시 그 순서로 도구를 선택하거나 유효 답변을 만든다는 보장은 아니다. 검사에서는 실제 예약 코드와 한 도구→유효 답변 scripted host를 사용하고, 실제 구독 실행은 별도로 확인한다. 2 steps를 도구 두 번에 써서 최종 답변을 못 받은 경우 성공 처리하지 않는다. 실제 읽기 receipt를 보존하고 `FINALIZE` 또는 승인된 추가 조사 subtask만 다음 명시 action에서 수행한다.

검색→원문 읽기→답변처럼 두 도구 round가 필요한 과제는 사전 계획된 3-step/2-tool ticket으로 구성하거나 한 번의 조사에서 보존한 실제 검색 결과를 다음 read/final 과제로 잇는다. 먼저 부족한 1 step으로 조사 역할을 시작해 놓고 답변 여유가 있다고 표시하지 않는다. 사용자 model 한도가 1이면 도구 없는 문제정의/질문/final만 가능하며 도구 조사 과제는 대기한다.

시간은 모두 같은 `deadline`을 쓴다. 새 host 시작에는 **남은 5초 이상**이라는 v2 admission guard를 둔다. 이는 새로 선택한 시작 정책이지 완료 시간 보장 또는 기존 제한 연장이 아니다. 이보다 짧으면 `WAITING_TIME`으로 보존한다. 실제 deadline·취소·호스트 cleanup 제한은 기존 구현을 따른다. retry만 새 명시 attempt 예산을 갖고, 자동 timer가 budget을 갱신하지 않는다.

### 4.4 `BudgetSlice`와 실제 `_Budget.reserve_provider_steps` 접점

A는 `BudgetSlice`를 전용 runtime 모듈에 작성한다. 각 slice는 기존 root `_Budget`의 **같은 RLock·deadline·counter**를 참조한다. root는 현재 action에서 생성한 slice만 승인한다. 모델 입력이나 JSON에서 slice를 만들 수 없다.

공통 파일의 변경은 다음 형태로 고정한다.

```python
# 기존 API의 keyword default는 보존한다.
_Budget.reserve_provider_steps(
    *, allowed_consultations=0, correction=False, _allocation=None
) -> int

# _ask/run_openscience가 받는 객체의 기존 호출 형태는 바꾸지 않는다.
BudgetSlice.reserve_provider_steps(
    *, allowed_consultations=0, correction=False
) -> int
BudgetSlice.consume(kind: str) -> None
```

`_allocation=None`이면 현재 legacy 예약 수식과 동작을 그대로 사용한다. 팀 slice는 `_allocation=self`로 **바로 그 root 메서드**를 호출한다. root 메서드는 다음을 하나의 root lock 안에서 검사·반영한다.

- slice의 root/action/task/actor 결속, active 여부, 현재 deadline을 검증한다.
- root 잔여와 slice 잔여, 해당 actor에 계획한 잔여, 아직 시작하지 않은 다른 ticket의 보호 몫을 함께 검사한다.
- 일반 호출은 해당 ticket의 `invocation_steps`만 예약한다. 별도 배정 없이 남은 예산 대부분을 가져가는 legacy 추정을 팀 경로에 사용하지 않는다.
- 기존 Co-STORM Completion은 `correction=True`를 단일 completion 예약에도 사용한다. 따라서 그 flag 자체를 형식 교정 허가로 해석하지 않는다. `REPAIR`, `MAP_SERVICE`, `REPORT_SERVICE`의 명시 slice에서는 용도에 맞게 1 step만 예약하고, EVIDENCE/ANSWER slice가 이를 이용해 별도 repair 몫을 가져가는 것은 거절한다. 실제 형식 교정은 REPAIR ticket에서만 수행한다.
- root `used_models`, slice `used_models`, 해당 actor reservation과 `used_model_host_invocations`를 동시에 증가시킨다. 하나라도 초과하면 **counter 변경·host 실행 모두 0**이다.
- 예약 receipt가 기존 owner checkpoint에 durable 저장된 다음 host를 시작한다. 저장 실패 시 host 0이며 보수적으로 남은 예약을 환불하지 않는다.

다른 ticket의 보호 몫은 `AllocationPlan`의 아직 시작하지 않은 배정이다. 이것은 실제 provider charge가 아니다. task가 입력/권한 때문에 시작 전 취소되면 계획된 대체 경로(REPAIR/서비스)로 그 **미예약 몫**을 재배정할 수 있고 새 plan revision을 먼저 남긴다. 이미 host에 예약한 steps는 실제 사용이 적어 보여도 재배정/환불하지 않는다.

`consume('tool'|'consultation'|'model')`도 같은 root lock 아래 root와 slice 상한을 함께 검사한다. Haystack의 모델 step은 consume 경로, OpenScience는 선예약 경로다. 한 호출을 두 경로에서 이중 차감하지 않는다. `used_evaluations`는 기존 root 공유 값이며 actor별로 초기화하지 않는다. 전용 테스트는 fake budget 구현이 아니라 이 root 메서드와 slice의 결합을 사용해야 한다.

기본 `consultations=0`이면 실제 상담 도구는 노출하지 않는다. 초기 barrier가 닫힌 동안에도 consult를 노출하지 않는다. 양의 자문 예산이 있어도 다른 조사자의 결론이 초기 독립 입력에 섞이는 경로는 열지 않는다. 사용자에게 명시 허용된 자문은 `caller host 2 + target host 2` 이상을 사전 배정하고 consultation 1·양측 tool scope·target 세션·의존성을 함께 결속한다. 외부 caller가 target 몫을 선점할 수 없으며 recursion/visited 제한은 유지한다. 자문 몫이 없으면 기존 `experts.consult`를 무허가 호출하지 않고 X의 대상 질문 task로 남긴다.

### 4.5 action별 배정 순서와 4/8의 유한 진행 예

기본 일정은 필요한 초기 조사·교차 질문·답변 ticket을 먼저 채운다. 그 뒤 남은 steps를 **공용 서비스 몫**으로 배정하고, 서비스 안에서는 이미 발생한 응답의 REPAIR → pending MAP 순서로 사용한다. REPORT는 별도의 명시 report action에서만 실행한다. 서비스 몫이 0이면 그 action에서 교정·지도 모델 호출은 0이다. 지도 삽입을 역할 수행의 숨은 비용으로 넣지 않는다.

다음 표는 동일 phase, 초기 조사 역할 3개 R1/R2/R3, 각 조사에서 실제 허용 도구 1회, R3의 대상 질문 Q, R1의 도구 기반 답변 A를 계획한 정상 경로다. 모든 답변은 검증 성공하고 필요한 scope/시간이 충분하다는 **수용 fixture 조건**이며 실제 AI 성공 보고가 아니다. 지도는 role 응답과 분리되어 서비스 몫 안에서만 전진한다.

| 명시 모델 한도 | action | 배정 | 모델 최대 / 최소 실제 전용 도구 수 | 완료 후 남은 과제 |
|---:|---|---|---|---|
| 4 | 첫 시작 | R1 조사 2 + R2 조사 2 | 4 / 2 | R3 초기 조사, Q, A. 지도 pending; 다른 역할 결론은 R3에 아직 전달하지 않음 |
| 4 | advance 1 | R3 조사 2 + Q 1 + 서비스 1 | 4 / 1 | barrier 개방 후 Q 생성. A는 2가 필요하므로 시작하지 않음 |
| 4 | advance 2 | A 답변 2 + 서비스 2 | 4 / 1 | 초기 3조사→특정 주장 Q→근거 답변/수정 완료. 남은 지도 작업은 별도 표시 |
| 8 | 첫 시작 | R1 2 + R2 2 + R3 2 + Q 1 + 서비스 1 | 8 / 3 | 세 초기 조사 완료 후 Q. A는 잔여 1로 시작하지 않음 |
| 8 | advance 1 | A 답변 2 + 서비스 최대 6 | 8 / 1 | 같은 연구 상호검토 완료. 실제 필요 없는 서비스 몫은 host에 예약하지 않음 |

각 action의 tool 상한은 기본 8 안이며, role 수만큼 초기화하지 않는다. runtime 상한이 8이어도 사용자가 4를 선택했다면 첫 세 행의 경로다. 위 경로는 초기 연구 3개+질문+답변에 필요한 모델 예약 9를 여러 명시 action에 나눈 것이며, 한 번의 4 또는 8로 전부 끝난다고 말하지 않는다.

서비스 1에서 KB 삽입에 모델 호출 두 번이 필요하면 첫 성공 Completion을 journal에 보존하고 지도 transaction은 공개하지 않는다. 다음 서비스에서 성공분을 replay하고 미완료 호출부터 잇는다(§8). REPAIR가 필요하면 Q/후속 답변은 barrier·응답 검증을 통과하기 전 시작하지 않는다. 관련 없는 완료 R1/R2를 다시 조사시키지 않는다.

### 4.6 이어가기·멈춤과 유한성

`TaskRecord.status`는 `PENDING, RUNNING, WAITING_BUDGET, WAITING_TIME, WAITING_FINAL, WAITING_REPAIR, BLOCKED_SCOPE, OUTCOME_UNCONFIRMED, COMPLETED, ACKNOWLEDGED_UNRESOLVED` 중 하나다. `completed_response_id`가 검증된 task는 다시 `_run_approved_role`에 전달하지 않는다. 미완료 final은 기존 도구 반환과 자기 입력만 사용한다. 진행자나 다른 역할의 결론을 몰래 넣어 초기 독립성을 바꾸지 않는다.

같은 주장에 새 근거 없는 반복이 2회면 새 자동 과제를 만들지 않고 미해결·다음 관측으로 정리한다. 모델이 질문을 반환했다고 무한히 새 task를 승인하지 않는다. `turn_limit`, 등록 역할, 이번 phase의 검토 목적과 명시 action 상한이 제한한다.

현재 action의 완료와 phase 완료를 구별한다. `WAITING_BUDGET`에서 화면은 “이번 범위 완료, 남은 조사 1·질문 1”처럼 실제 남은 과제를 표시한다. 사용자 명시 advance만 새 action 예산을 갖는다. 같은 command 응답 유실 확인은 기존 receipt 조회이며 신규 예산·host 예약이 없다.

### 4.7 실제 Co-STORM 역할 접합

`ConfiguredExpertAgent.generate_utterance`는 승인된 actor 하나만 실행하며 전체 원 응답·계획·읽기·입력 의존성을 먼저 checkpoint한다. `BoundDiscourseManager.get_next_turn_policy`는 §4.2의 초기 barrier와 task 일정을 따른다. dry_run은 조회만 하고 task/counter를 변경하지 않는다.

`should_update_experts_list=False`, `should_polish_utterance=False`, `should_reorganize_knowledge_base=False`를 팀 기본으로 둔다. 이 플래그들이 upstream의 삽입을 막는다고 가정하지 않는다. 무조건 삽입은 §8의 `DeferredKnowledgeBase`가 처리한다. 진행자의 의미 있는 질문도 등록 actor/task로 실행하며, unbound 일반 agent·임의 생성 전문가·simulate_user로 fallback하지 않는다.

실제 사용자가 입력한 첫 Guest turn을 owner identity로 한 번 보존한 뒤 실제 `CoStormRunner.step()`을 호출한다. 새 팀 초기화는 승인된 역할의 독립조사로 warm-start를 대신한다. 일반 Co-STORM의 실제 `warm_start()`는 현재 기능대로 보존한다.


예약 counter와 실행 관측도 구별한다. 기존 `used_model_host_invocations`의 선예약 의미는 바꾸지 않고, v2의 `observed_host_invocations`는 실제 `run_openscience` 어댑터 호출 경계에서 따로 증가시킨다. 어댑터 호출 또는 CLI 시작이 실제 provider inference/청구를 증명하지는 않는다. `completed_host_replies`와 실패 단계를 함께 기록하고 관찰 불가능한 billed model calls/tokens는 null이다. durable 예약 저장 실패 뒤 host를 부르지 않은 경우 observed 값은 0이다.

## 5. 분야 자료·검색과 응답 전체의 안전한 공유

### 5.1 코퍼스 구성·갱신·적용성

새 자료 묶음은 기존 KnowledgeStore로 명시 반입하는 **버전별 문서 목록·원문·범위·출처 기록**이다. 새 vector DB, embedding 다운로드, RAG 서버를 만들지 않는다. 실제 본문을 읽지 않은 목록은 `DISCOVERY_ONLY`이며 코퍼스 구축 완료로 세지 않는다.

| 자료 묶음 | 우선 내용 | 적용·갱신 한계 |
|---|---|---|
| solver-calculix | 설치 버전의 요소·재료·접촉·하중·출력·수렴 설명과 공개 검증 예제 | 웹 latest를 설치 solver의 명세로 자동 대체하지 않음 |
| pre-freecad-fem | 설치 버전의 FEM model/mesh/material/load/constraint/solver 입력 | tutorial·소스·설치 버전 차이를 별도 표시 |
| mesh-gmsh | physical group, 요소차수, 메시 크기·품질, 형식·절점 순서 | 다른 버전/개발판 규칙을 무조건 적용하지 않음 |
| post-paraview | data association, component/location/block, time, filter/chart, 원결과 복귀 | 그림만으로 point/cell/IP·성분·시간을 추정하지 않음 |
| impact-solver | 현재 고정된 무료 solver의 실제 keyword·출력 정의·사용 가능한 매뉴얼 | 공개 링크와 설치본 동일성, 원본의 보존 상태를 구별 |
| material-testing | 선택 실험 문서·법칙 근거·시험 방법·공개 논문 | 단위/측도·방향/공정·온도/속도·시편·fit/holdout 조건 구별 |
| project-selected | 현재 선택한 문서·Data/Material/Study·실제 결과 | 전체 프로젝트·미선택 폴더 수집 금지 |

문서마다 제목·저자/기관·원 URL/DOI·발행/획득일·도구/버전·문서 종류·실제 license/notice·원 bytes·선택 text/locator·추출 한계·supersedes·검토 상태를 남긴다. 저작권/무료 가용성이 확인되지 않은 전문은 배포하지 않는다. 기존 문서 metadata와 새 추출/적용성 평가를 섞지 않는다.

갱신은 사용자의 명시 `자료 갱신 확인`에서 실행해 새 revision을 만든다. 기존 citation은 원 revision에 남는다. 철회/정정은 현재 사용 경고로 연결하고 원 raw 기록·사용자 판단을 몰래 바꾸지 않는다. 라이선스·최신 문헌 상태를 이번 설계에서 새로 조사한 것은 아니다. 첨부된 이전 설계의 출처 확인 원칙을 유지한다.

### 5.2 기존 BM25와 단일 `ActionLiteratureAccess`

로컬 검색은 현재 허용된 exact source refs 안에서 기존 BM25L을 사용한다. 작은 양/영문 동의어 사전은 검색 보조일 뿐 원문·수식·solver keyword를 재작성하지 않는다. 검색 score, 실제 읽은 구간, 버전/물리조건 적용성은 서로 다른 항목이다. 원문 확인은 `knowledge.source`의 정확 locator를 사용한다. 역할의 selected source refs가 비어 있으면 로컬 검색은 명시 빈 결과를 반환하거나 선택 필요 상태로 끝내며, empty filter를 전체 KnowledgeStore 검색으로 해석하지 않는다. public topic-only/results-only의 로컬 검색·색인 재구축은 0이다.

공개검색은 현재 `8dddcb2`의 Literature/Crossref·SelectedRetriever·archive/locator·부분 성공 journal을 재사용한다. B는 이것들을 **공동 action 경계**로 묶는 `ActionLiteratureAccess`를 작성한다. 새 검색 공급자/클라이언트/embedding은 없다.

```python
ActionLiteratureAccess.search(request, *, caller, input_dependencies) -> BoundToolResult
ActionLiteratureAccess.read(request, *, caller, input_dependencies) -> BoundToolResult
```

`caller`는 owner가 검증한 actor 또는 진행자 component의 trusted binding이다. 역할의 직접 `literature.search/read`와 `SelectedRetriever` 모두 **동일 인스턴스/ledger**를 통과한다. SelectedRetriever에 선택적 keyword `public_access=None`을 추가한다. 팀 실행에서는 항상 제공하고, 일반 모드에서는 현행 기능을 유지한다. 팀 요청이 helper 부재 시 직접 Literature로 fallback하는 경로는 금지한다.

#### 공동 범위와 상한

현재 operator + 해당 질문의 `public_search` 허가와 참여 역할의 tool grant 검사를 유지한다. 역할별 조사가 가능하다는 이유로 기존 공개검색의 전원 허가 규칙을 완화하지 않는다. 공용 scope를 충족하지 못하면 로컬/결과 조사만 가능하며 사용자 명시 변경이 필요하다.

논리 action당 **실제 외부 search 시도 최대 2회, 각 결과 최대 4개 논문**이다. 성공·실패·취소된 외부 search 시도 모두 시작 전에 ledger에 차감한다. 캐시된 성공 search 재사용은 외부 시도 0이다. 같은 query라도 이미 실패한 network 작업을 재시도하면 남은 시도 몫을 사용한다. 두 시도를 소진하면 같은 action의 retry로 상한을 초기화하지 않는다. 새 일반 advance의 공개검색은 새 명시 action이지만 기존 성공 citation을 교체하지 않는다.

`top_k>4`, action의 세 번째 실제 query, 허가 없는 query는 외부 요청 전에 거절한다. 모델이 query 배열을 반환하면 각 query를 이 경계로 순서대로 처리한다. 허용된 앞 성공 결과를 뒤 상한/읽기 실패가 지우지 않는다. 관련 상태를 `PARTIAL`로 반환하고 나머지를 미실행으로 남긴다.

query 문자열 자체도 생성 입력 의존성을 가진다. 제한 자료로 만든 검색문을 인용 삭제/익명화 추정만으로 공개 엔드포인트에 보내지 않는다. 기존 전송 관문이 그 query의 전체 의존성 전송을 허용하지 못하면 거절한다. 공개 자료와 원 authored 공개 질문만을 사용하는 깨끗한 검색 경로는 정상 동작해야 한다.

#### 정확한 성공 작업 journal

`PublicSearchLedger`는 `{id,logical_action_id,attempt_count,entries,read_entries}`다. search entry key는 논리 action, provider, 정확 query, 정규화된 허용 filters, top_k, 계약판으로 구성한다. **actor는 key에 넣지 않는다.** 같은 승인 query를 역할과 진행자가 중복 호출해 외부 검색을 반복하지 않게 한다. 권한 fingerprint는 reuse 검증에 쓰지만 새 fingerprint만으로 과거 query slot을 삭제하거나 상한을 초기화하지 않는다.

외부 호출 전 `STARTED`와 요청을 durable 저장한다. 실제 성공 후 원 응답 bytes/정렬된 paper IDs/서지/정확 archive와 locator를 저장하고 `SUCCEEDED`로 바꾼다. 완료 여부를 모르는 STARTED는 `OUTCOME_UNCONFIRMED`다. GET이므로 안전하다는 이유로 읽기/poll에서 자동 반복하지 않는다.

read entry는 `{search_entry_id 또는 selected_archive_ref,paper_id,archive_id,locator,read_level,status,raw_ref,dependency_ids}`에 결속한다. 결과에 URL만 있으면 본문 읽음이 아니다. read request가 archive를 생략하면 **그 action이 이미 선택/보존한 정확 entry**로 해소한다. 최신 검색/최신 논문 상태를 다시 조회해서 해소하지 않는다. 명시 선택도 search 성공도 없는 임의 paper_id/URL은 scope 밖이다.

search 성공 후 특정 paper read가 실패하면 명시 retry는 성공 search와 성공 read를 재사용하고 실패 read만 수행한다. 새 검색 순위로 대체하거나 성공 read를 다시 가져오지 않는다. archive/locator 변조, 현재 권한 철회는 cached response에도 적용한다. 재사용 실패를 새 network 요청으로 자동 숨기지 않는다.

public read의 실제 호출도 root/slice tool budget 안이다. SelectedRetriever 내부에서 몇 번의 network search/read를 했는지 ledger에 기록하고 내부 tool 소비도 같은 root counter에 반영한다. 역할의 직접 호출은 바깥 `execute`가 소비한 1회 tool debit을 trusted permit로 전달하므로 같은 작업을 이중 차감하지 않는다. 추가 내부 read에는 추가 debit이 필요하다. 거절·실패도 시도한 tool 호출로 기록한다.

### 5.3 실제 입력 전체의 의존성 수집

B의 `GenerationLedger`는 모델 출력 내용 분석기가 아니다. A/root가 다음 공급 지점에서 알려 주는 **실제 입력·반환**을 기록한다.

| 입력 경로 | 기록할 범위 |
|---|---|
| 초기 prompt | authored 질문/담당 질문·역할 지시·선택 조건의 원 참조와 동결 bytes |
| 자동 자료 주입 | `_knowledge_context`가 실제 주입한 모든 snippets의 exact revision/segment/text 범위 |
| session history | 실제로 다시 보낸 user/assistant turn 전체와 각 응답의 생성 의존성 |
| 전달 질문·발언 | target claim/질문 원 응답 전체의 의존성. 인용된 몇 줄만 남겨도 감소시키지 않음 |
| 모든 tool 응답 | source/search/read/result/status/inputs/plan/analyze/consult 및 오류 응답 중 모델에 반환한 값과 그 생성 근거 |
| 결과 | exact retained owner/input/result 참조, 요청/실제 반환 selector·단위·측도·frame |
| consultation | target의 입력·반환 의존성의 전체 전이적 합집합. target이 적은 citation만 쓰지 않음 |
| map/report | 이전 승인 KB/보고서/발언 전체의 생성 의존성과 이번 추가 입력 |

도구 schema·role definition처럼 제품이 고정 공급한 내용도 버전/내용 fingerprint를 기록한다. 원 오류에 민감 경로/내용이 있으면 기록과 전송 scope를 확인하고, 허용되지 않은 메시지는 민감한 세부정보 없는 거절 상태로 바꾼다. 숨은 내부 reasoning을 수집하거나 보존할 필요는 없다.

Haystack의 `BeforeModel` 직전에 실제 메시지 payload·누적 의존성을 확정하고 현재 source/transmission을 검사한다. OpenScience는 host 호출 전 prompt를 검사하고, **모든 scoped tool 응답을 host에 돌려주기 직전** 누적 의존성과 현재 허가를 재검사한다. host 내부 모델 turn별 정확 계수는 알 수 없으므로 해당 invocation의 입력 의존성은 보수적으로 누적한다. 이미 전송된 bytes를 revoke가 소급 회수한다고 주장하지 않는다. 철회 관측 후 신규 전송/공유·재사용은 막고 기존 취소 경계를 적용한다.

응답을 받으면 그 task의 모든 입력 manifest를 합쳐 `RoleResponse.dependency_ids`에 결속한다. 읽었지만 모델에 전달하지 않은 보관용 bytes는 `read_receipt`에는 남지만 전달 범위 기록과 구별한다. 공급 여부가 불확실하면 의존성에 포함하거나 `UNVERIFIED`로 표시하고 공유를 막는다. 비어 있는 모델 `sources=[]`를 공개 응답의 증명으로 사용하지 않는다.

### 5.4 응답 단위 공유 — 문장별 의미 분리는 하지 않는다

`shared_projection(response, recipients, current_scope)`는 응답 전체의 의존성에 대해 기존 KnowledgeStore/문헌 archive/retained owner/전송 정책을 확인한다. 모든 수신자에게 현재 허용되는 경우만 본문을 반환한다. target 역할에 보낼 경우 그 역할, 공동 history/KB/보고서의 경우 해당 phase의 참여자·진행자 및 해당 출력의 현재 수신 범위를 검사한다. map 자체를 새 권한 주체로 만들지 않는다.

첫 버전에서는 **응답 전체 허용 또는 응답 전체 차단**이다. 제한 문장만 “안전하게 분리”하거나 민감 키/인용을 지워 허용하는 이전 문구는 폐기한다. 차단된 응답의 제목·claim·질문·Plan 내용도 공용 목록에 노출하지 않는다. 필요한 UI 상태는 “현재 공유 범위 밖 자료를 사용한 응답” 같은 비민감 표시다.

제한 원 응답은 기존 owner의 허용된 로컬 읽기에서만 보존·열람한다. 공용 `ConversationTurn`, history, KB, Report, portable 공개 미리보기에 먼저 넣고 나중에 화면에서 숨기는 순서는 금지한다. 공유 가능한 공개 응답의 정상 왕복도 필수 수용 조건이다.

별도 공개 답변이 필요하면 사용자 명시 `공개 자료만으로 새 조사`로 새 task/pass와 깨끗한 role session을 만든다. 입력은 원래 공개 허가된 authored 문제정의와 공개 자료만이다. 제한 응답·그 요약·그것을 읽은 session·그 응답으로 만든 질문/target·지도·cache/consult 결과를 전혀 넣지 않는다. 이전 제한 응답의 표현만 고치도록 시키지 않는다. 새 추론 비용은 해당 action의 기존 예산에서 지불한다.

### 5.5 철회·cached projection·retry·Report

projection/Completion/read cache를 반환하기 전, 새 모델 입력 직전, KB 삽입 직전/commit 직전, Report preview/export와 portable 수집/발행 때 현재 권한을 재검사한다. 의존성을 저장한 receipt 자체를 현재 허가로 신뢰하지 않는다.

어떤 자료가 철회되면 그 자료에 의존하는 응답·파생지도·보고서는 현재 공유 view에서 차단한다. 기존 raw asset을 수정하거나 인용을 지워 탈민감화하지 않는다. 이전 KB 전체가 그 자료에 의존하면 active KB 전체를 `BLOCKED_SCOPE`로 숨긴다. 개별 허용 발언은 여전히 읽을 수 있다. 사용자 명시 새 지도 작성은 허용된 응답만으로 **깨끗한 빈 KB**에서 시작하며 차단된 base snapshot/Completion journal은 가져오지 않는다.

source 누락과 scope 거부는 다르다. 기존 R1/P2의 허용 frozen 내용과 `SOURCE_UNAVAILABLE/navigation_reference=None` 원칙을 유지한다. scope 거부는 frozen/cache/export로 우회하지 않는다. source가 없다는 이유로 원 store 접속, 최신 revision 추정, 새 검색을 자동 수행하지 않는다.

### 5.6 분야 지식의 검증 수준

자료를 읽었다는 사실과 현재 업무에 맞다는 판단을 분리한다. 논문 제목/서지/초록만으로 재료상수·접촉조건·제작 적합성을 확정하지 않는다. 공개 전문이어도 시편·방향·공정·속도·온도·측도가 다르면 직접 적용 불가 또는 추가 시험으로 남긴다. 표준 번호를 찾은 것과 그 유료 전문을 읽은 것도 구별한다.

무료 열람, 무료 API, 전문 재사용/배포 라이선스, 코드 라이선스와 문서 라이선스는 서로 다른 필드다. 미확인 권리는 미확인으로 기록하며 전문을 제품에 동봉하지 않는다. 공개 corpus manifest는 실제 각 문서의 notice를 보존한다. 새 학습/API 구매 대신 실제 공식 항목과 선택한 논문, 사용자의 정확한 결과를 검토하는 데 범위를 둔다.

## 6. 두 대표 업무의 구체적 사용자 흐름

아래 입력/대화는 **계승한 전체 제품 수용 시나리오**다. 실제 회사 자료, 실행 결과 또는 계산된 수치를 제시한 것이 아니다.

### 6.1 업무 A — 강판 부품의 낙하 후 잔류변형 원인 연구

**주제 입력.** 사용자가 “시험보다 해석 잔류변형이 크다. 어떤 원인이 유력하며 무엇을 확인하면 구별되는가?”를 입력한다. 시험의 잔류형상/측정 위치·시간·좌표계, 선택된 해석 run과 응답, 재료시험 자료, 접촉/경계조건 설명을 붙인다. 빠진 입력은 빈칸을 임의값으로 채우지 않고 과제로 남긴다.

**팀 검토.** structures/testing/challenge를 기본으로 잡는다. 재료법칙 비교가 필요하면 materials, 조건의 영향 비교가 필요하면 numerical, 외부 사례 조사가 필요하면 literature를 넣는다. 각 역할에 “같은 물리량을 비교 중인가”, “초기 상태·속도·접촉 또는 재료 중 어떤 가설을 구별할 수 있나”처럼 담당 질문을 배정한다.

**독립 조사.** testing은 실제 측정이 강체운동 제거 후 값인지, 기준 좌표·관측 종료시각·영구변형 정의가 무엇인지 확인한다. structures는 실제 job 종료/부분시간, 선택 위치와 단위, 응답의 측도·좌표계·출력 위치, 경계/접촉 및 이용 가능한 에너지/반력 기록을 확인한다. materials는 시험조건과 카드 동정 근거를 읽는다. literature는 선택 모델·변형/접촉 가설과 맞는 문헌만 읽는다. numerical은 현재 결과가 인자 영향을 판별하기에 충분한지 검토한다.

**상호질문.** 예를 들어 구조 역할이 “잔류응력이 누락됐을 가능성”이라는 가설을 낸다. 반론 역할은 “현재 자료에서 초기속도·마찰·측정 기준 차이와 구별되는 근거가 있는가?”라고 해당 claim에 질문한다. 재료 역할은 보유 시험이 그 가설에 답할 수 있는 범위를 명시한다. 사용자 “해당 부품은 열처리를 하지 않았다” 또는 “그 측정은 다른 시점이다”라는 개입은 authored observation으로 보존되며 가설의 자동 사실화는 일어나지 않는다.

**판별 계획.** 각 가설에 필요한 관측과 예상되는 구별 패턴을 적는다. 초기조건 확인, 같은 기준으로 재측정, 허용된 마찰/입력 조건의 작은 DOE 등을 기존 `calculations.inputs/plan`으로 제안한다. solver가 초기응력 기능을 현재 backend에 노출하지 않으면 새 임의 card를 실행하지 않고 native에서 준비할 과제를 남긴다. 계산으로 구별할 수 없는 가설은 시험 계획으로 남긴다.

**실행.** 사용자가 한 제안의 `계산 계획 열기`를 누른다. 기존 정확한 turn/proposal→N transfer로 Plan을 연다. 인자 범위·단위·응답 위치·계산 수·리소스·지원 backend를 기존 Numerical 화면에서 검토하고 실제 실행을 명시 승인한다. 계획 작성과 저장에는 실행이 없다. 원 모델은 보존하고 새 run을 생성한다.

**후속 토론.** 완료 알림은 job 상태만 갱신한다. 사용자가 실제 retained 결과의 응답/위치/성분/시간을 선택하고 `연구에 결과 추가`를 누른다. 현재 전송 범위를 검토한 뒤 같은 X의 다음 phase에서 numerical이 실제 결과/실패 행을 읽고, structures/testing/challenge가 앞서 기록한 판별 조건과 대조한다. 가설이 수정되면 이전 claim에 revision을 연결한다. DOE에 반영한 인자만 검토됐다는 한계를 유지한다.

**마감/보존.** Study에 후보 가설별 supporting/conflicting evidence, 판단, 미해결, 다음 관측을 사용자가 명시 채택한다. “한 원인 확정”이 불가능하면 UNKNOWN 또는 조건부 판단으로 남긴다. Report는 원측정·실제 result·문헌 locator·서로 다른 주장·마지막 미해결을 포함한다. 저장/새 process/이동 사본 재열기에서 같은 판단과 근거를 읽고 새 Ask만 현지 권한으로 가능해야 한다.

**사용자 관점 종료조건.** 최소 한 주장에 대해 다른 역할의 대상 지정 질문과 근거를 읽은 답변/수정이 존재하고, 원인 후보와 판별 시험/계산이 연결된다. 실제 결과를 하나 추가한 뒤 앞선 판단을 유지 또는 수정한 이유를 확인할 수 있다. 근거 부족으로 원인을 확정하지 못해도 작업은 유효하게 종료될 수 있다.

### 6.2 업무 B — 제작 전 시험 지그의 설계·해석 검토

**주제 입력.** 사용자 FreeCAD 지그 조립 또는 매개변수화 가능한 기초 형상, 시편/시험기 연결부, 시험 목적, 예상 하중 범위, 이동·간섭 영역, 제작 재료/공정·방향, 허용 변형/정렬 조건을 선택한다. 이 설계는 자연어만으로 검증된 CAD가 자동 생성된다고 약속하지 않는다. 현재 native 입력이 없으면 먼저 실제 FreeCAD에서 설계를 작성할 과제로 연결한다.

**팀 검토.** design/structures/testing/challenge를 기본 후보로 하고, 3D 프린팅·비등방성/장기 하중 등 재료 검토가 필요하면 materials, 여러 후보 비교가 필요하면 numerical, 관련 방법 조사가 필요하면 literature를 넣는다. 구조 응력 하나가 아니라 시편에 원하는 하중이 전달되는지와 지그의 계측 영향까지 담당 범위에 넣는다.

**조사.** design은 실제 조립·체결·시편 삽입/교체·공구 접근·유격/공차 자료를 확인한다. structures는 하중 경로·구속·접촉·지그 및 시편의 응답 정의를 검토한다. testing은 필요한 측정/정렬 조건과 지그 변형의 영향 관측을 제안한다. materials는 실제 제작조건에서 물성이 확보됐는지, 문헌 시편과 같은 조건인지 확인한다. 공개 AM 논문/보고서는 후보 근거이지 현재 프린트 지그 물성 증명서가 아니다.

**상호질문.** “최대응력이 낮으므로 제작 가능”이라는 주장이 나오면 반론 역할은 지그 유연성, 편심, 접촉 가정, 출력방향별 재료 근거와 허용기준을 묻는다. materials는 자료가 없는 방향/장기거동을 미확인으로 남긴다. testing은 “강성은 충분해도 시편에 부가 굽힘이 생기는가?”라는 관측 가능한 질문을 design/structures에 보낸다.

**변경/계획.** 현재 backend가 노출하는 기존 design parameter만 `calculations.inputs`로 확인한다. 지지 간격/두께/배치 등 typed 변수의 계획을 만들고, 실제 형상 변경은 기존 FreeCAD 속성/스케치/조립 편집과 명시 Apply로 수행한다. Gmsh mesh와 solver는 기존 native 경로로 준비한다. 등록되지 않은 CAD 조작을 새로운 shell 또는 모델 생성 코드로 우회하지 않는다.

**계산.** 후보별 geometry/mesh/load/constraint/material/response 정의를 기존 owner에서 검토하고 필요 시 명시된 작은 후보 비교를 실행한다. 현재 수용 기준의 출처와 허용값은 사용자가 제공하거나 자료로 근거를 지정한다. 임의의 안전율/허용 변형을 모델이 확정하지 않는다. 계산 실패·메시 민감성·접촉조건 불확실성은 성공 후보 뒤에 숨기지 않는다.

**결과 검토.** 사용자는 ParaView의 실제 객체/블록·성분·위치·시간을 기존 결과 선택으로 열어 확인한다. 이미지와 색범위만이 아니라 정확한 reader 결과를 연구에 붙인다. 팀은 후보 변경이 응력/강성/정렬/제작 가능성에 미친 영향을 읽고 앞선 반론에 답한다. 필요한 시험은 소형 시편, 지그 단독 강성 확인, 조립·정렬 확인 등 근거에 맞게 제안하되 실제 수행 전에는 계획이다.

**종료.** Study에 “제작 후보로 유지/수정 필요/기준 또는 근거 부족”을 명시 기록한다. 공학 release는 기존 정책과 사용자 판단을 따르고 모델 응답만으로 NOT_RELEASED를 바꾸지 않는다. Report에는 후보 설계와 실제 해석 조건, 읽은 물성 근거, 남은 시험·제작 검증과 각 판단의 출처를 포함한다. 파일을 이동해도 native 미설치 상태에서는 보존 결과를 읽을 수 있고 새 native 실행은 readiness/허가를 다시 확인한다.

**사용자 관점 종료조건.** 하나의 실제 후보 설계에서 지그 기능과 구조 응답을 구별하고, 반론에 따라 한 번 이상 설계/계획 또는 판단을 수정한다. 실제 solver 결과가 그 과제에 다시 연결되고, 미확인 제작조건을 승인으로 둔갑시키지 않은 채 저장/재열기가 된다.

### 6.3 두 업무에 동일하게 적용할 교정 계약

초기 조사와 대상 질문은 §4의 barrier·실제 4/8 예산 일정으로 진행한다. 제한 자료를 읽은 역할의 주장/가설/계획은 전체 생성 의존성을 검사한 뒤만 공유한다. 해석/시험 결과는 §9.2 exact selector로 읽고, 수치분석은 §9.3 명시 scope를 통과해야 한다. 지도 반영이 실패해도 완료한 조사·Plan·원 응답은 읽을 수 있으며 다음 명시 retry는 지도만 수행한다. 어느 업무에서도 문헌이 없다는 이유만으로 검증된 결과 기반 검토나 문제정의 시작을 막지 않는다.

## 7. Native Qt 화면과 실제 조작

### 7.1 기존 창에서 시작한다

`ExpertWindow`의 기존 문서/파일 메뉴와 toolbar 안에 `연구팀` 모드를 추가한다. 새로운 독립 토론 프로그램, 브라우저 탭, localhost 웹 UI를 만들지 않는다. 시작 화면에는 연구 질문 입력, 자료/결과 추가, 팀 검토, 연구 시작이 있다. 모드를 바꾸어도 옛 sequential/Co-STORM 기록은 보존한다. 기존 문서를 소급 변환하지 않고 새 연구 단계로 시작한다.

정상 폭에서는 기존 splitter를 사용해 **왼쪽 논점/과제, 가운데 발언과 입력, 오른쪽 원자료/결과**를 둔다. 좁은 창에서는 논점과 자료 영역을 탭으로 접는다. 최소 폭보다 더 좁은 전체 고정 테이블을 강제하지 않는다. 지도는 예쁜 그림만 제공하지 않고 keyboard로 선택 가능한 tree와 동일한 선택 상태를 사용한다.

상단에는 현재 단계·실제 선택 모델·진행 중인 역할·남은 예약 상한·사용자 확인 대기를 표시한다. 내부 hash, session 문자열, raw JSON은 접힌 진단 영역에만 둔다. `3명 답변 완료`와 `근거 검토됨`, `해석 성공`과 `제작 승인`을 서로 다른 상태로 표시한다.

### 7.2 팀·자료 검토

`팀 검토`는 역할, 이번 담당 질문, 볼 자료, 사용할 도구, 미충족 조건을 행으로 보여준다. 행을 선택하면 담당 질문을 편집하고 source picker로 exact 자료/결과를 선택한다. 현재 등록되지 않은 역할/미설정 모델은 실행 가능한 것처럼 체크하지 않는다. 구성·자료 선택의 저장은 inference를 하지 않는다.

`자료` 탭은 문헌 제목·개정/버전·실제 읽은 범위·출처·현재 상태를 표시한다. 클릭하면 기존 source preview로 해당 page/section/segment를 연다. 초록과 본문을 같은 표시로 합치지 않는다. 사용자가 회사 자료를 로컬에서 검토하더라도 이번 설계의 외부 모델 검사에는 전달하지 않는다. 로컬 표시 허용과 외부 전송 허용은 기존 선택 화면에서 구별한다.

`결과` 탭은 owner/실행 시점/계산 상태를 먼저 선택하고, 실제 reader가 제공하는 응답·성분·위치·시간·단위·측도를 선택하게 한다. 없는 성분/위치를 직접 문자열로 만들어 통과시키지 않는다. 변형 그림의 선택과 원 값의 선택은 동일한 typed selection에 연결한다. 기존 Post의 current navigation 실패, native 미지원 범위는 그대로 노출한다.

### 7.3 발언·반론·사용자 개입

발언은 실제 역할, 수행한 과제, 발언 종류, 겨냥한 주장/발언, 실제 읽은 자료 수, 도구 수행 결과, 유효/미확인 인용 상태를 표시한다. 본문 아래의 `근거`, `반론`, `질문`, `계획`은 실제 선택 가능한 항목이다. 도구 이름만 길게 나열하지 않고 `선택 결과의 Z변위 읽음`, `논문 초록만 확인`, `계산은 제출하지 않음`처럼 실제 결과를 표시한다.

사용자는 발언/주장을 선택하고 `이 주장에 질문`, `반례 추가`, `관측 추가`, `담당자 지정`을 사용할 수 있다. 각각 기존 composer의 reply_to/classification/evidence와 research-team target을 명시 작성한다. 사용자 원문은 `expert.intervene`로 append-only authored turn에 들어간다. AI가 작성한 질문을 사용자 발언으로 표시하지 않는다.

`개입 반영`을 누르면 진행 중인 연구는 다음 역할 시작 전에 멈추고, 새 입력과 자료 범위를 검토한 **다음 명시 action**에서 개입을 소비한다. 이미 제출된 role prompt 또는 round prepared_arguments를 몰래 수정하지 않는다. 현재 질문과 단순 답변의 범위를 넘는 새 자료/역할/전송 조건은 새 phase로 처리한다. 제한된 action 안에서 이미 승인된 agent 간 질문·응답은 사용자에게 매번 수동 재전송시키지 않는다.

### 7.4 버튼의 의미

| 표시 | 실제 동작 | 하지 않는 일 |
|---|---|---|
| 연구 시작 | 현재 질문/팀/자료·budget 검토 후 기존 expert.ask 1회 | solver 자동 승인, 전체 프로젝트 수집 |
| 다음 발언 / 범위 내 진행 | 현재 phase에서 표시된 발언 수와 기존 budget의 expert.advance | polling에 의한 무제한 계속하기 |
| 다음 연구 단계 | 변경한 팀/자료/결과를 검토·작성하고 새 phase의 Ask | 과거 source/session/job 재활용 |
| 일시 정지 | 기존 pause flag + 다음 내부 역할 시작 금지 | 실행 중인 다른 solver/user 창 종료 |
| 현재 응답 중단 | 기존 JobManager의 해당 AI job 취소 요청 | 실패를 성공 처리하거나 원 job 자동 retry |
| 재개 | pause 해제; 이후 진행 버튼 활성화 | 재개 버튼만으로 inference/solver dispatch |
| 중단 작업 다시 시도 | 현재 local attempt의 미완료 부분만 명시 retry | 이미 완료된 역할/검색/계산 반복 |
| 계획 열기 | 기존 정확한 발언/제안의 Numerical Plan 열기/생성 | Plan 실행, CAD Apply |
| Study에 반영 | 선택 주장·근거·미해결/다음 관측을 기존 S에 명시 적용 | AI 다수결로 판단/NOT_RELEASED 변경 |
| 보고서 정리 | 명시 예산 안에서 Co-STORM 보고서 초안 또는 기존 문서 편집 | 미읽기 문헌/모델 추론을 확정 결과로 승격 |
| 저장 / Undo / Redo | 현재 authored 편집과 기존 owner 저장 계약 | 실제 발생한 provider/solver 사건을 지우거나 되돌림 |

일반 `새로고침`/poll은 표시 갱신과 현재 local job의 검증된 완료 응답 수집만 한다. 모델·검색·index 재구축·새 작업 제출은 0이어야 한다.

### 7.5 편집 손실과 오류 표시

현재 composer/제목/판단의 미적용 문자열은 별도 buffer로 유지한다. source 선택·계획 열기·창 전환·copy 버튼이 암묵 Apply하지 않는다. 필요한 경우 기존 `현재 편집 저장 후 포함 / 저장된 내용만 / 취소`를 사용한다. invalid draft의 저장은 허용하지만 연구 실행 관문은 통과시키지 않는다.

늦은 응답은 제출 당시 phase/task/input generation에 붙는다. 사용자가 현재 수정 중인 질문·선택·Study 결론을 바꾸지 않는다. 화면에는 `이전 조건으로 받은 응답`과 원 제출 질문을 보여준다. 다중 창 generation 충돌에는 현재 buffer와 새 owner 상태를 나란히 검토하고 명시 재적용한다. 파일/저장 실패는 성공 표시로 덮지 않는다.

`현재 권한 거부`일 때는 원문·캐시 미리보기·Report export로 우회 노출하지 않는다. `자료 누락`일 때는 권한상 표시 가능한 frozen 내용과 현재 탐색 불가를 구별한다. 존재하지 않는 원 store를 자동으로 찾아가거나 최신 문서를 대체 표시하지 않는다.

### 7.6 기본4·남은 과제·지도 pending을 실제 조작으로 표시

팀 검토에는 “이번 모델 처리 상한 4 / 도구 상한 8”과 “이번 범위에서 최대 조사 2개, 남은 조사·질문은 다음 진행”을 표시한다. 실제 청구횟수나 미래 실행시간을 추정해 약속하지 않는다. 상한8은 사용자가 현재 허용 범위에서 명시 선택한 경우에만 표시한다.

발언 목록과 별도로 `조사 완료 / 답변 마무리 대기 / 다음 조사 대기 / 지도 반영 대기 / 현재 공유 불가`를 구별한다. pending 지도에서는 **지도 반영 다시 시도**가 원 역할을 재호출하지 않는다. 마지막 승인 지도와 아직 반영되지 않은 허용 발언을 나란히 선택할 수 있다. 철회된 지도는 민감한 과거 미리보기를 보여 주지 않는다.

`공개 자료만으로 새 조사`는 현재 제한 응답을 공개한 것으로 처리하지 않고 별도 깨끗한 task/session의 초안을 만든다. 사용자는 실제 자료/수신 범위를 검토한 후 기존 연구 시작/진행을 누른다. 결과 선택은 같은 run이라도 정확한 성분·위치·시간을 보여 주고, 범위 밖 요청의 오류는 현재 선택과 원문 buffer를 보존한다. 수치분석 허가는 별도 명시 선택이며 일반 연구 시작에 따라 자동 체크되지 않는다.

## 8. 실제 upstream step·지도 transaction·중단과 복구

### 8.1 단일 선택 — `DeferredKnowledgeBase`

pinned `CoStormRunner.step`은 agent 응답 뒤 history에 append하고 무조건 `knowledge_base.update_from_conv_turn`을 호출한다. 실제 KB 삽입은 모델을 호출하고 인용 문자열도 바꾼다. `should_reorganize=False`로 이 동작이 없어지지 않는다.[REQ4][REV4]

**선택한 유일한 접합은 instance별 `DeferredKnowledgeBase` proxy다.** vendor 파일/전역 class/다른 runner를 수정하거나 monkeypatch하지 않는다. 팀 runner의 `knowledge_base`에 이 proxy를 연결하고, proxy 안에 직전 승인 KB snapshot과 owner-bound pending writer를 둔다.

```python
DeferredKnowledgeBase.update_from_conv_turn(
    conv_turn, allow_create_new_node=True, insert_under_root=False
) -> None                 # provider/실제 KB 삽입 0, pending checkpoint만
DeferredKnowledgeBase.reorganize() -> None   # 서비스 요청만 등록
DeferredKnowledgeBase.to_dict() -> dict      # 현재 허용된 승인 snapshot만
apply_pending_map(pending_id, *, binding, budget_slice) -> MapApplyResult
```

proxy의 read delegation은 사전에 검사한 read-only KB 메서드/속성에만 허용한다. 임의 `__getattr__`로 `to_report/reorganize/update` 등 생성·변경 메서드가 우회 실행되지 않게 한다. `to_report`는 명시 report service 없이 호출하면 거절한다. projection/summary를 읽는다고 모델 호출이 발생하지 않는다. 지도 추가가 필요해도 역할 응답을 다시 생성하지 않는다.

### 8.2 역할 응답부터 pending까지의 고정 순서

하나의 역할 task에 대해 다음 순서를 따른다.

**A. 역할 실행·원본 checkpoint.** `_run_approved_role`의 실제 응답, 도구·읽기 receipt, 입력 manifest, Plan, 검증 상태를 owner action asset에 durable 저장한다. 이 checkpoint에 성공해야 정상 완료 응답으로 간주한다. 해당 시점부터 현재 허용된 로컬 원문/계획을 읽을 수 있다. 모델은 성공했으나 checkpoint 전에 process가 죽었다면 `OUTCOME_UNCONFIRMED`이지 재호출 가능한 성공이 아니다.

**B. 공유 투영.** §5.4로 응답 전체를 검사한다. 차단되면 `COMPLETED_LOCAL / BLOCKED_SCOPE`로 보존하고 `ConfiguredExpertAgent.generate_utterance`는 `None`을 반환한다. 실제 pinned step의 `conv_turn is not None` 분기 밖에서 끝나므로 민감한 placeholder 발언도 history/KB에 넣지 않는다. UI의 차단 상태는 비민감 owner 상태다.

**C. 실제 step.** 허용된 응답은 `SharedProjection`과 안정된 `event_id/response_id/projection_id`를 먼저 checkpoint하고 그 투영의 **새 ConversationTurn 사본**을 반환한다. 실제 `CoStormRunner.step()`이 그 사본을 history에 한 번 append한다. 연구팀 전용 turn wrapper/side table이 event ID와 projection ID를 연결한다. 원 role response 객체를 그대로 반환하지 않는다.

**D. 무조건 삽입의 지연.** step이 부르는 proxy의 `update_from_conv_turn`은 투영·현재 권한·event binding을 확인하고 그 turn을 다시 복사해 `MapPending`만 저장한다. 실제 KB에 삽입하지 않으며 인용 문자열도 바꾸지 않는다. pending 등록 실패는 map/기록 실패이지 role 재실행 이유가 아니다.

`MapPending`의 필드는 다음으로 고정한다.

```text
id, phase_id, response_id, shared_projection_id, event_id,
conversation_turn_ref, cited_information_refs, dependency_ids,
allow_create_new_node, insert_under_root,
base_map_revision, journal_ref, status, last_error, applied_map_revision
```

`status`는 `PENDING`, `APPLYING`, `WAITING_BUDGET`, `WAITING_TIME`, `FAILED`, `BLOCKED_SCOPE`, `APPLIED`, `ARCHIVED_PENDING`이다. `base_map_revision`은 최초 삽입 attempt에서 고정하고 성공 전까지 바꾸지 않는다. 동시에 여러 지도 writer를 두지 않으며 FIFO의 가장 오래된 pending 한 개씩 처리한다.

vendor `ConversationTurn.to_dict()`만으로 `cited_info`가 복구되지 않으므로 `cited_information_refs`에 실제 Information archive와 원 인용 대응을 별도 보존한다. 복구 때는 이 ledger로 사본의 `cited_info`를 다시 결속한다. AI가 새 인용번호를 추측하게 하지 않는다.

### 8.3 지도 삽입 transaction

`apply_pending_map`은 기존 Co-STORM 자료구조/LM adapter/encoder를 사용한다. 새 지도 엔진이 아니다.

1. pending이 current-local이고 현재 owner/action/job가 허가한 것인지 검증한다. 원 response/projection/근거와 base KB의 **전체** 생성 의존성을 재검사한다. 원 pending을 복사해 얻은 local 실행 권한은 없다.
2. 직전 승인 base snapshot bytes를 읽어 새로운 임시 `KnowledgeBase` 인스턴스를 만든다. base가 없는 첫 지도는 빈 KB다. pending turn/Information도 복사한다. 승인 snapshot 또는 원 response 객체를 in-place 변경하지 않는다.
3. 공유 서비스 slice를 사용하는 tracked Completion을 결속하고 실제 vendor `KnowledgeBase.update_from_conv_turn`을 이 임시 사본에 호출한다. 반복 model 요청마다 현재 권한/예산을 재검사한다. 순서·encoder·정보 ID/삽입 입력은 보존된 값으로 고정한다. 기존 runner의 관련 worker/thread 한도는 1로 설정하고 tracked Completion의 단일 호출 lock을 공유해 지도 내부에서도 모델 동시 실행 1을 지킨다.
4. 실제 반환 뒤 구조·인용 해소·정확 source mapping을 검증하고 현재 권한을 다시 확인한다. `MapCheckpoint` asset을 durable 저장한 다음 owner lock 안에서 기대 base revision과 pending status를 CAS 확인한다.
5. CAS 성공한 하나의 checkpoint만 active map pointer로 공개하고 해당 pending을 APPLIED로 기록한다. pointer와 적용 기록은 같은 action checkpoint revision에 들어간다. 응답 유실 때 이 revision으로 같은 결과를 재확인한다.

원 인용 문자열은 그대로다. vendor가 변경한 문자열·번호는 `MapAppliedTurn/citation_map`이라는 파생 표시로만 저장한다. 원 응답·원 Plan·원 read receipt 또는 원 발언의 인용 namespace를 재작성하지 않는다. Report가 사용하는 KB 번호와 원 발언 번호 사이에 실제 exact mapping을 둔다.

### 8.4 실패·예산소진·취소·재시도

첫 삽입 실패, 일부 Information 삽입 후 실패, 모델 예산 소진, deadline/취소가 발생하면 임시 KB 전체를 버리고 active map pointer를 바꾸지 않는다. **완료 role response, Plan, 도구/읽기 receipt, 공유가 허용된 원 발언은 그대로 남는다.** UI에는 “응답 완료 / 지도 반영 대기·실패”를 분리 표시한다.

성공한 Completion과 source/search/read journal은 현재 권한으로 재검증 가능한 원 asset으로 남긴다. 지도 journal key에는 pending ID, base map revision, actor/component, 실제 model 설정, input/protocol fingerprint, 정확 prompt/의존성 입력이 결속된다. 새로운 actor·다른 base·다른 권한 입력의 응답을 키가 비슷하다고 재사용하지 않는다. 실패한 응답 자체의 형식 때문에 거절된 경우 해당 entry만 invalid로 표시한다.

명시 retry는 **같은 pending/base/response**에서 새 임시 KB를 만들고 성공 journal을 replay한다. 이미 성공한 모델 completion과 search/read의 외부 호출은 0이며 미완료 model/read만 현재 서비스 예산으로 실행한다. 지난 실패 attempt의 이미 차감한 steps는 환불하지 않고 새 명시 attempt 예약은 따로 기록한다. 검증한 cached completion 반환은 새 provider step을 차감하지 않는다.

첫 버전은 pending당 서로 다른 지도 Completion 항목 최대 32개, 기존 전체 journal/asset 상한 이하로 제한한다. 이 숫자는 현재 vendor의 보장치가 아니라 새 팀의 보호 상한이다. 초과 시 `MAP_COMPLEXITY_LIMIT`로 미해결을 남긴다. 짧은 서비스 몫을 여러 번 승인해도 매번 성공 prefix를 재호출하지 않으며, 실패를 숨기는 무한 자동 retry는 없다.

완료 role task를 복구할 때 `runner.step()`나 `generate_utterance()`를 다시 호출하지 않는다. `reconcile_checkpoint`가 원 response에서 공유 투영/pending 등록만 결정적으로 복구한다. history는 owner의 `shared_turn_ids`를 안정 event ID 순서로 재구성하므로 step append 직후 process가 죽어도 동일 응답을 두 번 append하지 않는다. text equality로 중복을 판정하지 않는다.

`ExecutionCleanupFailed` 또는 실제 host 종료 미확인은 별도 `OUTCOME_UNCONFIRMED`로 남긴다. 반환 raw가 있더라도 재사용 가능한 정상 응답으로 승격하지 않는다. 기존 Windows helper가 확인한 자기 process 수명 경계를 따른다.

### 8.5 최신 시작 호환성 — 문헌 필수 관문을 되살리지 않는다

`8dddcb2`에 반영된 **주제 + operator/해당 질문/역할 public_search 허용**, 또는 **검증된 계산 결과만으로 시작**하는 owner 관문을 유지한다.[REQ5] 원 설계의 “legacy Co-STORM selected_sources required 유지” 문장은 폐기한다. 팀 분기 밖의 최신 public topic-only/results-only 경로도 회귀 시험 대상이다.

| 현재 명시 입력 | 정상 동작 | 표시할 한계 |
|---|---|---|
| exact knowledge 있음 | 기존 local/BM25·선택 원문 조사. 허용 시 공개검색도 사용 | 실제 읽은 revision/locator와 적용성 |
| verified result만 있음 | exact 결과를 읽고 조사 시작; 문헌 selection 없음 허용 | 원문 문헌 없음, 결과가 답하지 못하는 조건 |
| public search 허용, local/result 없음 | 공개 topic-only 탐색 시작 | 검색 0건/서지만/초록만을 실제 확보 수준대로 표시 |
| 자료/검색 허가 없음 | 팀의 문제정의·필요자료 정리 또는 수동 작성 | 근거 기반 결론/RAG 완료로 표시하지 않음 |
| 모델 미설정 | 같은 Qt에서 자료·과거 기록 읽기/작성/Undo/save | 새 inference 미실행; 원 질문 보존 |

빈 source 목록은 전 store 검색/외부검색 허가가 아니다. result-only도 job ID 하나만으로 전 채널 읽기가 허용되지 않으며 §9.2 범위를 따른다. source-backed branch의 최신 안전장치·부분 성공 journal·원 archive/locator를 축소하지 않는다.

### 8.6 checkpoint·현재 owner·pause/late response

새 저장 엔진 없이 기존 X 폴더의 `research-team/<round_id>/action.json`과 선언된 bounded assets를 사용한다. `discussion_research_team.authorize`는 `checkpoint`, `read_checkpoint`, `control_status`와 좁은 도구 factory를 trusted request에만 제공한다. 외부 모델/API 인자로 callable 또는 저장 경로를 받지 않는다.

checkpoint는 현재 local owner/session, job/request/operation, 원 prepared arguments, checkpoint revision을 확인한다. 짧은 owner lock 아래 atomic write/CAS만 수행하고 provider/network를 기다리지 않는다. 사용자가 draft를 편집했어도 이미 제출한 task의 원 입력 결속이 유효하면 늦은 실제 응답을 그 원 task에 보존한다. 현재 draft generation에 맞지 않는다는 이유로 새 편집을 덮거나 실제 과거 결과를 잃지 않는다.

pause는 다음 내부 역할 시작을 막고, 현재 응답 중단은 해당 AI job의 취소 요청이다. resume는 pause 해제만 하며 새 inference는 명시 advance가 한다. 새 사용자 개입은 다음 실행 입력을 검토하게 하고 이미 제출한 prompt를 몰래 수정하지 않는다.

### 8.7 상태와 권한 철회

작업 상태는 DRAFT/READY/RESEARCHING/AWAITING_USER/AWAITING_PLAN/AWAITING_RESULT/PAUSED/BLOCKED/PARTIAL/REVIEW_READY를 유지한다. 그 아래 role/task 완료, map pending/applied, report current/stale를 독립 표시한다. `REVIEW_READY`는 필요한 검토 응답이 보존됐다는 뜻이며 지도/보고서가 아직 대기할 수 있다. 모든 것이 완료된 것처럼 단일 초록 상태로 합치지 않는다.

철회된 pending은 BLOCKED_SCOPE이며 shared KB에 삽입하지 않는다. 이미 승인한 base KB가 그 자료에 의존하면 현재 KB/보고서 view도 차단한다. 이전 bytes는 불변 보존하되 현재 읽기 정책으로 보호한다. 허용된 다른 응답의 로컬 읽기·편집·다음 과제는 계속할 수 있다. 깨끗한 지도 재작성은 §5.5의 별도 명시 동작이다.

### 8.8 command 유실응답과 portable pending

같은 현지 command는 기존 receipt/request/arguments 일치 검사로 결과만 재확인한다. map commit 또는 role checkpoint 후 응답 유실도 신규 provider/검색/삽입 없이 복구한다. 같은 command에 다른 입력을 넣으면 충돌이다.

portable에 보존된 원 action/task/pending은 `archived_origin`이며 원 상태·bytes를 유지한다. 현지 표시용 pending 상태는 ARCHIVED_PENDING이고, 원 prepared arguments/JobManager/session/Completion journal을 현지 resume 승인으로 쓰지 않는다. 원 job lookup·harvest·retry·자동 dispatch는 0이다. 현지 새 phase/Ask가 현재 registry/source/transmission/실행 허가를 새로 통과한 뒤 생성한 job만 정상 완료 수집·같은 command 유실응답 재확인이 가능하다.


### 8.9 보고서 생성도 명시된 파생 작업이다

기존 `CoStormRunner.generate_report()`를 실제 사용한다. 명시 report action에서만 임시 runner/현재 허용된 승인 KB와 tracked Completion을 결속하고 proxy의 report service guard를 연다. 이 guard 밖의 `to_report` 호출은 거절한다. 원 응답·현재 draft·active KB를 보고서 생성 중 in-place 변경하지 않는다.

보고서의 성공 component journal은 현재 입력/모델/의존성에 결속해 재사용한다. 실패·예산소진·취소 때 이전 유효 보고서와 원 역할 응답을 유지하고 보고서만 pending으로 남긴다. 다음 명시 retry는 성공분을 재호출하지 않고 미완료 생성만 수행한다. 보고서 출력 전체는 그 base KB와 실제 공급 발언/자료의 생성 의존성을 계승한다. 현재 공유되지 않은 role 원문을 더 완전한 보고서를 만들겠다는 이유로 추가하지 않는다.

## 9. 실제 도구 범위·Plan·결과 환류·Study·Report

### 9.1 계산 제안과 실제 실행

기존 `calculations.inputs`는 현재 지원 입력을 보여 주고 `calculations.plan`은 기존 형식의 편집 가능한 제안을 만든다. Plan에는 원 task/claim, 판별할 관측, 조건·범위·한계가 연결된다. 이 관계는 provenance이며 새 solver 설정 key가 아니다.

`ExpertWindow.connect_desktop_actions`의 exact discussion/turn/proposal→Plan 전송과 안정된 command_id를 재사용한다. 지도 text에서 제안을 다시 추출하지 않는다. `discussion_costorm.collect`의 팀 분기는 실제 role 응답의 proposed_actions·read/tool 기록을 보존하며 빈 제안으로 치환하지 않는다.

사용자는 기존 Numerical/Simulation 편집기에서 실제 backend·원 frozen 모델·변수·단위·결과 정의·평가 수·threads/memory를 검토하고 명시 실행한다. `_request_plan_arguments`, `_proposed_submit`, Numerical owner 및 native typed 준비/검증 경로를 유지한다. 새 arbitrary backend/shell/solver 또는 자동 CAD Apply는 없다.

기본 연구 역할의 실제 실행 도구는 비활성이다. 기존 operator의 넓은 `allow_execution`만으로 이번 질문/Plan을 자동 승인하지 않는다. 이번 scope·backend·변수/원 입력·자원 한도를 만족해야 한다. 계산제안/계획 저장/연구 시작/결과 알림은 실제 실행 승인이 아니다.

### 9.2 exact result/selector에 결속된 trusted reader

현재 job ID 위주 검사만으로 같은 run의 다른 성분·위치·행·시간까지 허용되는 틈을 막는다. 새 결과 store는 만들지 않는다. 기존 Workbench retained-owner fallback과 실제 source owner/result reader를 사용한다.[REQ3][REV3]

#### 자료형

```text
ResultSelection = {
  source_id: owner가 발급한 이번 역할의 선택 토큰,
  reference: {
    document_id, job_id, input_revision, input_sha256, result_sha256
  },
  selector: CanonicalSelector,
  descriptor_ref: 기존 owner/reader의 검증된 응답 정의 참조,
  read_limits: {max_rows, max_values, max_bytes}
}
```

strict `reference`의 기존 5개 key를 바꾸지 않는다. selector/단위/측도는 바깥 wrapper에 둔다. `source_id`는 모델이 이번에 읽을 수 있는 선택지를 지칭하는 토큰일 뿐 authority가 아니다. Qt에는 문서·실행 시각·물리 응답명을 보여 주며 사용자가 토큰/hash를 입력하지 않는다.

`CanonicalSelector`는 `{metadata_only, channels[]}`이다. 각 channel 절은 `{response, association, component, location_ids, frame_indices, row_intervals, unit, measure, frame, coordinate_system}`을 가진다. 관련 없는 축은 null이며 의미를 모르는 값을 `global` 등으로 추측해 넣지 않는다. 원 reader가 실제 제공한 응답/association/component/location만 선택 가능하다.

- `row_intervals`는 원행 identity 기준의 0-based 반열림 `[start,stop)` 범위다. source reader가 다른 표현을 쓰면 C의 명시 compile helper가 원행 대응을 보존해 변환한다.
- 시간 구간 UI는 기존 저장된 시간/프레임 descriptor를 이용해 정확한 `frame_indices`로 바꾼다. 중복 시각도 원 frame identity를 유지한다. nearest frame, 보간, 다른 프레임 평균을 몰래 수행하지 않는다.
- location은 기존 reader의 실제 entity/leaf/IP/row identity다. native assembly/block selector는 기존 최신 Post 경로가 주는 값을 보존한다. 이 설계가 새 selector 문자열 또는 옛 CompositeDataSetIndex를 만들어 넣지 않는다.
- requested selection은 승인 selector의 **물리 샘플 집합 부분집합**이어야 한다. component/location/시간을 각각 union해 허용되지 않은 교차조합을 만들지 않는다. 예: X@A와 Y@B를 허용했다고 X@B가 허용되지는 않는다.
- unit/measure/frame/coordinate_system은 원 definition과 일치해야 한다. 단위·측도 변환/축 회전/추가 reduction은 단순 read가 아니며 기존 명시 변환/분석 경로에 맡긴다.

첫 positive read fixture는 표/시계열과 기존 지원 native field를 각각 포함한다. 지원 reader가 표현하지 못하는 요청은 `UNSUPPORTED_SELECTION`으로 남기고 그 사실을 Qt에 표시한다. 지원되는 정확 선택을 일괄 차단해서 완료 처리하지 않는다.

#### 호출과 검사 순서

팀 mode의 `results.read`는 호출별 도구 schema로 `source_id`와 선택적 `selection`을 받는다. 기존 `job_id`형 요청도 **해당 job에 정확히 한 ResultSelection이 있을 때만** 호환 해소한다. 두 형식을 동시에 보내거나 같은 job에 선택이 여럿인데 token 없이 요청하면 거절한다. 모델이 reference/hash를 새로 적어 권한을 늘릴 수 없다.

binding의 `prepare_tool`은 숫자 payload reader 호출 전에 아래를 수행한다.

1. 현재 assignment 안의 source token/유일한 legacy job 해소. session `generated_jobs`는 현재 scope에 자동 합치지 않는다.
2. 기존 owner의 저장 revision/retention 검증으로 실제 document/run/input/result identity와 요청의 신뢰된 reference를 대조한다. 입력이 주장하는 hash를 실제 hash로 채택하지 않는다.
3. 검증된 response descriptor로 request를 canonicalize하고 승인 selector 부분집합·byte/row/value 한도를 확인한다. selection 생략은 **승인된 그 선택**을 의미하며 run 전체로 확장하지 않는다.
4. 현재 result/source 전송 허가를 재검사하고, C의 `read_selected_result`에 exact reference와 canonical 선택만 전달한다.
5. 기존 reader의 안정된 retained snapshot/입력 identity 검사와 읽기 전후 무결성 검사를 유지한다. 실제 반환의 owner/input/result 및 성분·위치·행·시간·단위/측도를 requested selection과 비교한다. 더 넓거나 다른 결과, metadata-only로의 몰래 대체, unsupported fallback은 모델에 반환하지 않는다.

2번의 저장 bytes/manifest 검증은 숫자 payload 열람 callback과 구별한다. C가 `probe_retained_result`를 기존 owner 검증에 연결해 authoritative reference와 descriptor를 제공한다. 변조된 reference/hash 또는 selector 범위 위반은 실제 `read_selected_result` 호출 0이어야 한다. 저장 내용 변조도 기존 retention 검증을 통과하지 못한다. 안전한 참조 검증을 생략하고 전체 result를 먼저 읽은 뒤 잘라서 scope를 맞추지 않는다.

기본 prompt용 read_limit은 `max_rows=1024, max_values=16384, max_bytes=20000` 이하이며 기존 runtime/reader의 더 낮은 제한이 우선한다. 큰 자료는 현재 선택 안에서 명시 구간을 줄여 읽는다. 조용히 첫 몇 행만 읽고 전체 결과를 읽었다고 표시하지 않는다. 별도 승인된 분석은 §9.3의 자체 입력 상한으로 기존 로컬 reader를 사용할 수 있으나 모델 payload 상한은 늘어나지 않는다.

반환 `ExactResultReceipt`는 `{id,reference,requested_selector,returned_selector,definition_ref,verification,status,payload_ref,payload_digest,limitations}`이다. `verification='VERIFIED'`는 실제 허용 선택과 원본 검증을 뜻하며 수치 계산의 적합성은 아니다. 실패·부분 result는 원 상태와 실제 반환 범위로 기록한다.

### 9.3 `numerical.analyze`를 실제 gate에 연결한다

분석은 solver 제출이 아니어도 계산이다. 기존 `numerical.analyze → Workbench._execute` 직접 callback을 팀 모드에서 무검사 호출하지 않는다. 일반 기존 API를 전부 재작성하지 않고 §10의 호출별 hook이 이 도구를 선행 검증한다.

#### 명시 scope

사용자가 기존 계산 허가 영역에서 `선택 결과의 수치 분석 허용`을 명시 선택한 경우에만 다음 값을 기존 `context.calculation_scope`에 동결한다. AI가 만든 같은 이름의 dict는 허가가 아니다.

```text
calculation_scope.allow_execution = true
calculation_scope.resources = {threads: 1, memory_mb: 64}  # 같은 명시 검토에서 허용한 외곽 상한
calculation_scope.analysis = {
  operation: "analyze",
  source_ids: [승인된 ResultSelection 토큰],
  response_definitions: [기존 analyze schema를 통과한 정확 응답 정의],
  options: {},
  limits: {
    max_calls: 1, max_rows: 2048, max_columns: 16,
    max_input_bytes: 1048576, max_output_bytes: 262144
  },
  resources: {threads: 1, memory_mb: 64},
  request_revision: 명시 검토한 승인 입력의 기존 revision
}
```

이 수치는 첫 버전의 보수적 **허용 최대값**이며 사용자/operator의 더 작은 값이 우선한다. analysis.resources는 기존 calculation_scope.resources 및 현재 executor 상한의 부분집합이어야 한다. 외곽 resource 허가가 없으면 하위 analysis 값만으로 승인하지 않는다. scope가 없거나 allow_execution이 false, 또는 tool allowlist에서 analyze를 빼면 도구를 노출하지 않는다. 직접 dispatch를 시도해도 `_execute` 전에 거절한다. `allow_execution=true`만 있고 `analysis`가 없는 경우도 거절한다. 이 analysis scope는 solver/backend 실행 허가가 아니므로 기존 backend/Plan 실행 gate를 열지 않는다.

첫 버전의 `options`는 빈 dict만 받는다. 현재 analyze가 공식 schema로 제공하지 않는 option/method/코드를 모델이 invent하지 못한다. 선택 응답 정의·통계 의미는 기존 analyze/Plan validator를 그대로 사용한다. 특정 operator·reduction을 추가하려면 기존 지원 schema와 사용자 scope 둘 모두에 있어야 하며 이번 helper가 수학을 새로 구현하지 않는다.

#### dispatch 순서

`prepare_analysis(request, binding)`은 source_id, 승인 응답 정의와 옵션/자원을 확인한다. 모델이 직접 만든 `table/candidates/values`, 임의 파일 경로, 미선택 job, 승인 밖 행/열/응답을 계산 입력으로 받지 않는다. 모델의 숫자를 원 결과인 것처럼 계산하지 않는다. 사용자 작성 데이터도 기존 Data/Table owner에 명시 보존·선택한 실제 원자료여야 한다.

입력 종류는 기존 분석 engine이 실제 수용하는 retained Numerical/표 결과로 제한한다. C가 원행·실패행·변수/응답 의미를 유지해 기존 analyze 입력으로 resolve한다. 임의 native field를 그럴듯한 후보 표로 변환하지 않는다. 그런 변환이 필요하면 기존 Plan/측도/후처리 기능을 명시 사용한다.

source reference/selector·metadata의 크기·응답 정의·resource 상한을 먼저 검사하고, 승인된 실제 입력을 resolve한 뒤 실제 행/열/bytes와 source 무결성을 한 번 더 확인한다. 요청 전체를 고정한 `PreparedAnalysis`를 만든 다음 root가 연결한 **기존 callback을 한 번** 호출한다. 그 callback만 현재 `Workbench._execute('analyze', ..., 'read')`를 수행한다. prepare나 preview에서는 실행 0이다.

`PreparedAnalysis`의 필드는 `{id,scope_revision,source_receipt_ids,operation,validated_inputs,resources,limits,input_dependencies,request_digest}`이다. 모델에 전달하는 객체가 아니다. binding이 소비한 max_calls/tool budget·동일 요청 ledger를 확인한다. 성공 계산 응답이 durable 보존됐으면 같은 요청 재확인/retry는 그 응답을 읽고 `_execute`를 다시 부르지 않는다. 성공 여부 미확인은 자동 재계산하지 않는다.

threads와 입력 크기 등은 기존 resource admission/실행 통제에 전달한다. `memory_mb=64`를 Python RSS의 새 OS 강제 제한이라고 주장하지 않는다. hard 메모리/선점 timeout이 필수로 주어진 환경에서 기존 executor가 이를 제공하지 못하면 inline 분석을 실행하지 않고 기존 실행 가능한 Plan 경로로 보낸다. 취소/deadline은 현재 실행통제의 token을 공유한다. 새 process pool/worker 서비스를 만들지 않는다.

실제 반환은 `AnalysisReceipt`와 input_dependencies에 결속해 보존한다. 모델에 넘길 반환 크기는 이 분석 상한과 기존 runtime payload 상한의 작은 값 이내여야 한다. 초과하면 실제 계산 성공 기록은 남기되 전체값 전송을 거절하거나 기존 검증된 제한 표시를 사용하고 생략 범위를 명시한다. 성공 계산을 출력 크기 때문에 자동 재실행하지 않는다. 현재 허용 결과의 작은 정상 분석도 반드시 `_execute`를 실제 호출해 성공 경로를 검사한다. scope 없음/초과/모델 합성 표의 반례만 막는 것으로 완료 처리하지 않는다.

### 9.4 나머지 도구와 `_ask`의 호출별 축소

`knowledge.search/source`는 역할의 선택 revision/locator와 collection, `calculations.status`는 명시한 current run의 허용 상태만, `calculations.inputs/plan`은 기존 등록 schema만 허용한다. 상태 읽기 권한으로 원 질문/입력/다른 결과를 반환하지 않는다. 모든 도구 반환을 §5.3의 입력 ledger에 기록한다.

`experts.consult`는 승인된 target·별도 session·visited·예산 allocation과 source 범위를 지킨다. target의 자료 범위를 parent 전체로 넓히지 않는다. 좁은 수신자에게 제한 질문을 넘기는 기존 거절을 유지한다. target 생성 입력의 전체 의존성이 caller 응답에도 합쳐진다. 직접 실행 도구는 기존 실행 gate에 더해 이번 task/Plan의 축소 범위를 검사한다.

v2에서는 session의 과거 `generated_jobs`를 `allowed_result_ids`에 자동 추가하거나 status 조회로 권한을 재구성하지 않는다. 현재 사용자/assignment에 정확히 선택한 결과와 이번 명시 승인 Plan의 반환 receipt만 다음 explicit selection 후보가 된다. 옛 job ID 하나가 현재 모든 component/time 접근 권한을 뜻하지 않는다.

### 9.5 실제 결과 환류와 Study

source task/claim → 실제 proposed Plan → 기존 Plan 생성 receipt → 실제 submitted run/input/result → 선택 response/component/location/time → 다음 review task를 보존한다. 이름이 같은 job, latest run, 예상 계산값을 원 결과 대신 사용하지 않는다.

완료 알림은 read-only다. 사용자가 실제 결과를 선택하고 현재 전송 범위를 검토한 뒤 `결과로 후속 검토`로 같은 X의 다음 phase 초안을 만든다. 새 Ask 전에는 모델 호출 0이다. 기존 가설·판별 조건과 실제 결과를 대조해 keep/revise/withdraw/undetermined와 이유를 남긴다. 실패행·부분시간·누락 채널도 보존한다.

Study 반영은 사용자 명시 Apply로 기존 S의 질문/가설/support/conflict/판단/next observations를 편집한다. 원 X 발언·정확 결과/문헌 참조를 유지한다. AI가 사용자의 판단·candidate 채택·UNKNOWN/NOT_RELEASED를 자동 변경하지 않는다. S의 update/Undo/Redo/save 계약을 재사용한다.

### 9.6 Report와 portable closure

Co-STORM 보고서 초안은 기존 Report owner의 편집 가능한 섹션으로 전달한다. 원 발언/Plan/지도 번호/문헌 locator/실제 결과·그림 조건은 정확한 참조로 연결한다. 지도/보고서 실패가 마지막 유효 원문을 지우지 않으며, scope 철회는 cached preview/export에 동일하게 적용한다. R1/P2의 원 A raw/PNG/frozen 참조와 현재 navigation 재검증을 유지한다.

`portable_research_knowledge/owner`의 기존 closure를 v2의 생성 의존성·phase/task·응답·질문/반론·Plan/result·map pending/approved snapshot·Completion/search/read journal까지 선언적으로 확장한다. 입력 전체 의존성에만 있고 모델 인용에는 없는 원문도 누락하지 않는다. 그 의존성의 복사 허가가 없으면 해당 파생 내용도 공개 미리보기나 export로 유출하지 않는다.

original raw bytes와 submitted/input/result hash는 재작성하지 않는다. 현재 탐색은 별도 typed mapping이다. 원 workspace/collection/access_scope/session/provider 설정은 현지 grant가 아니다. 원 session 파일·token·PID·자격증명·active dispatch 권한은 복제하지 않는다.

원 store/provider 없이 첫 별도 process에서 허용된 원문/토론·Study/Report·composer를 읽고 편집/Undo/save한다. 재복사 후 첫 사본도 차단한 두 번째 별도 process에서 원 기록과 현재 편집을 다시 읽는다. 원 pending의 현지 자동 실행은 0이며, 명시 새 local Ask의 정상 완료 수집과 같은 command 유실응답 확인은 유지한다. CB04–08, candidate/current 비교·부분 opener·managed native 잔여를 이번 완료로 바꾸지 않는다.

## 10. 개발자가 그대로 연결할 최종 인터페이스

이 절은 새 제품 코드가 아니라 **작성할 내부 Python 계약**이다. 기존 `ExpertRuntime.ask`의 공개 schema, 기존 document command의 빈 progression arguments, owner/result의 strict 참조를 유지한다. callable은 trusted 객체로만 전달하며 JSON/문서/portable에 직렬화하지 않는다.

### 10.1 호출 흐름

```text
기존 document command/CAS
  → discussion_costorm.start_record / authorize (v2 분기)
  → discussion_research_team.start_record / authorize
  → 기존 JobManager experts.ask + owner_step
  → costorm.run (trusted v2일 때만 run_team_action)
  → run_team_action: AllocationPlan / BoundDiscourseManager / DeferredKnowledgeBase
  → 실제 CoStormRunner.step
  → ConfiguredExpertAgent.generate_utterance
  → ExpertRuntime._run_approved_role(..., binding)
  → 기존 _ask(..., _binding=binding)
      - 입력 manifest / current source check
      - per-call tool schema·permit / 실제 기존 callback
      - 원 response checkpoint
  → shared_projection → 실제 step의 history append → proxy pending 등록
  → 허용 서비스 몫의 apply_pending_map → 승인 checkpoint만 공개
  → 기존 collect / UI / Plan / Study / Report / portable
```

### 10.2 A — 계약·owner·예산·runtime·지도

`caelab/research_team_contract.py`:

```python
enabled(draft) -> bool
validate_draft(draft, registry) -> list[Diagnostic]
validate_reply(raw_response, *, task, allowed_references, read_receipts) -> ReplyValidation
source_closure(team_record) -> list[ExactReference]
```

`enabled`는 v2만 실행 가능으로 판정한다. v1/unknown을 legacy로 조용히 실행하지 않는다. pure validation에서는 provider/search/쓰기 0이다. `source_closure`는 §3.6의 runtime manifest/의존성 기반 선언적 closure이며 현재 승인 검사는 B/owner가 한다.

`caelab/discussion_research_team.py`:

```python
normalize_update(current, proposed_draft) -> dict
start_record(owner, document, command_id, *, action, turn=None) -> dict
authorize(owner, arguments, job_id) -> TrustedAction
checkpoint(binding, *, expected_revision, event_id, payload) -> CheckpointReceipt
reconcile_checkpoint(binding) -> Reconciliation
collect(owner, document, record, run, response, state) -> bool
```

`TrustedAction`의 필드는 `owner_id, owner_session_id, phase_id, action_id, attempt_id, job_id, frozen_request, read_checkpoint, checkpoint, control_status, make_role_binding, public_access, result_access, analysis_access`다. 이전 pipeline의 trusted request 안에 이 객체를 넣는다. origin archive에는 발급하지 않는다. 수집은 stable event/task/response ID로 idempotent하고 current authored draft를 바꾸지 않는다.

`caelab/assist/research_team.py`:

```python
run_team_action(runtime, definition, question, context, session, path,
                workspace_id, budget, trusted) -> dict
plan_action(frozen_phase, tasks, *, limits, pending) -> AllocationPlan
ConfiguredExpertAgent.generate_utterance(knowledge_base, conversation_history)
    -> ConversationTurn | None
BoundDiscourseManager.get_next_turn_policy(conversation_history, dry_run=False,
    simulate_user=False, simulate_user_intent=None) -> TurnPolicySpec
```

기존 반환 envelope에 `costorm.team` v2와 역할/과제/예산·지도 상태를 붙인다. 실제 역할 응답의 proposed_actions/read/tool 기록을 잃지 않는다. snapshot/export/read 자체는 runtime을 호출하지 않는다. 진행 정책 actor와 실제 입력 범위는 registry+현재 assignment로 제한한다.

`BudgetSlice`는 이 모듈 또는 A 전용 내부 하위 모듈에 둔다. 외부 API는 §4.4 두 메서드다. 기존 `_ask`가 읽는 `model_calls/tool_calls/consultations/used_models/used_tools/used_consultations/used_model_host_invocations`는 slice 한도/사용량이고 `deadline/lock/used_evaluations`는 root 공유 값이다. 전체 action 통계는 root counters로 보고한다. 그 차이를 UI에서 실제 청구량으로 해석하지 않는다.

`AllocationPlan`은 `{action_id,model_limit,tool_limit,consult_limit,deadline,turn_limit,tickets[],service_pool,revision}`이다. ticket은 `{id,task_id,actor_id,kind,invocation_steps,model_steps,tool_calls,consultations,protected_for_others,status}`다. 정상 일정의 비용은 §4.3–4.5와 일치해야 한다. 아직 target이 확정되지 않은 Q ticket도 허용 actor/kind/상한은 계획되어 있으며 실제 target/입력 동결 후에만 실행한다.

`caelab/assist/research_team_map.py`:

```python
DeferredKnowledgeBase(approved_snapshot, *, binding)
register_pending(binding, *, projection, turn_copy, flags) -> MapPending
apply_pending_map(pending_id, *, binding, budget_slice) -> MapApplyResult
rebuild_shared_history(binding) -> list[ConversationTurn]
```

`MapApplyResult`는 `{status,pending_id,previous_revision,committed_revision,completion_receipts,error}`다. status는 APPLIED/WAITING_BUDGET/WAITING_TIME/FAILED/BLOCKED_SCOPE 중 하나다. 성공 role 응답에 대한 retry는 이 함수 또는 deterministic reconciliation만 호출하고 `generate_utterance`/step은 다시 호출하지 않는다.

### 10.3 A/root → B: 호출별 `ApprovedRoleBinding`

다음 helper와 `_ask`의 keyword 하나를 고정한다.

```python
ExpertRuntime._run_approved_role(
    expert_id, question, context, session_id, *, workspace_id,
    budget, visited, binding
) -> dict

ExpertRuntime._ask(
    definition, generator, question, context, session, path,
    workspace_id, budget, visited, *, _binding=None
) -> dict
```

`_binding=None`은 기존 정상 Expert 경로다. 팀 helper는 항상 owner가 만든 binding을 전달한다. helper는 실제 registry와 current model을 다시 확인하고 해당 호출용 definition/context만 축소한다. runtime definitions/callbacks나 전역 session을 임시 수정하지 않는다.

`ApprovedRoleBinding`의 필드:

```text
owner_id, owner_session_id, phase_id, action_id, attempt_id, task_id, actor_id,
role_session_id, frozen_task_ref, assignment, initial_visibility,
budget_slice, permitted_source_refs, result_selections, current_scope_probe,
generation_ledger, public_access, result_access, analysis_access,
checkpoint, control_status
```

public config/credential/profile은 model 선택에만 사용하고 위 저장 상태에 복제하지 않는다. `initial_visibility='independent'`이면 같은 phase의 다른 actor 응답/KB를 빼고 자체 과제 입력만 사용한다. `Assignment.mode`는 `investigator|coordinator`로 고정한다. investigator 모두가 초기 barrier에 속하고 coordinator는 별도의 독립조사 task를 자동 만들지 않는다. 진행자의 모델 질문을 요청한 경우 별도 ticket을 배정한다. §4의 3역할 예에는 진행자에 숨은 모델 호출을 더하지 않는다.

binding의 메서드:

```python
tool_parameters(name, legacy_schema) -> dict
prepare_history(session_turns) -> list[BoundMessage]
prepare_consult(target_id, question, *, visited) -> ApprovedRoleBinding
prepare_model_input(payload, *, mode, supplied_items) -> ModelInputManifest
prepare_tool(name, request, *, debit) -> ToolPermit
finish_tool(permit, returned_or_error) -> BoundToolResult
finalize_response(raw_response, validation) -> RoleResponse
validation_failed(raw_response, errors) -> ReplyValidation
```

`prepare_history`는 history 전체 생성 의존성을 현재 scope로 검사한다. legacy `read_sources`만 있고 새 입력 provenance가 없으면 team model context에는 넣지 않는다. 초기 조사 history는 새 phase의 자기 미완료 입력만 가능하다.

`prepare_model_input`은 실제 공급한 값과 runtime이 붙인 source reference/manifest를 받는다. supplied_items를 모델이 작성하지 않는다. `validation_failed`는 raw를 checkpoint하고 미완료 repair를 등록한다. `_ask`가 남은 root 예산을 보고 임의 repair host를 실행하지 못하게 이 지점에서 팀의 명시 repair ticket 정책을 적용한다.

### 10.4 root의 `_ask.execute` 최소 hunk

공통 execute를 복사하지 않고 다음 네 지점을 넣는다.

1. `tool_parameters`로 모델에 광고한 schema와 실제 dispatch validator가 사용하는 schema를 같은 호출별 값으로 고정한다. schema validation 이후 해당 slice에서 tool debit을 원자적으로 소비하고 `_binding.prepare_tool`을 호출한다. 거절되면 기존 callback/reader/네트워크를 부르지 않는다.
2. permit가 `GUARDED`이면 permit가 가진 trusted callable만 실행한다. `results.read`, `literature.search/read`, `numerical.analyze`는 v2에서 반드시 GUARDED다. 실패하거나 helper가 없을 때 legacy callback으로 fallback하지 않는다.
3. 나머지는 `EXISTING` permit의 canonical request로 기존 분기를 실행한다. knowledge/source/status/plan/명시 계산/consult의 기존 검사를 유지하며 binding이 더 좁힌 조건을 앞에서 확인한다. 단, v2 `experts.consult`의 마지막 역할 호출은 `prepare_consult`가 발급한 target binding/별도 session/하위 slice로 `_run_approved_role`에 위임한다. 기존 parent session_id의 transient dict를 그대로 쓰거나 `_binding` 없이 target `_ask`를 호출하지 않는다. caller가 생성한 자문 질문은 그 시점의 caller 입력 의존성 전체에 결속하고 target 반환 의존성을 caller ledger에 합친다.
4. 성공·실패 반환 모두 `finish_tool`에서 실제 receipt·누적 의존성·반환 범위를 검사하고 durable 기록한 뒤 모델에 전달한다. 종전 sources/tool_events/proposed_actions 요약 형식은 유지하되 새 trusted receipt를 추가한다.

`ToolPermit`은 `{id,tool,canonical_request,dispatch='GUARDED'|'EXISTING',invoke,current_binding_id,debit,dependency_ids}`다. `invoke`는 내부 callable이며 모델 출력에 있으면 무시한다. `BoundToolResult`는 `{payload,read_receipts,dependency_ids,status,limitations}`다. 허용 밖 payload를 먼저 모델에 준 뒤 검사하지 않는다.

기존 session generated_jobs를 읽어 allowed_result_ids를 늘리는 초기화는 `_binding is None`일 때만 유지한다. v2의 coarse job-ID 목록은 result_selections에서 파생시키되 **실제 reader gate는 exact selector**다. 현재 세션에 과거 job가 있다는 이유로 results/status/analyze callback을 먼저 호출하지 않는다.

OpenScience 호출 전 prompt, Haystack BeforeModel, 형식 교정, 모든 tool 반환과 세션 재사용의 입력 계측은 이 binding으로 연결한다. `openscience_host.py`와 Windows helper를 새로 만들지 않는다. 기존 host의 제공 도구는 동일 callable wrapper를 받으므로 출력 의존성/권한 검사가 bridge 반환 이전에 수행된다.

### 10.5 B — 자료·의존성·검색·공유 helper

`caelab/assist/research_evidence.py`:

```python
role_context(assignment, frozen_request, *, runtime, workspace_id,
             visibility, accepted_responses) -> BoundContext
GenerationLedger.add_supplied(item, *, dependencies, origin) -> DependencyRef
GenerationLedger.begin_model(payload, *, mode) -> ModelInputManifest
GenerationLedger.finish_model(manifest_id, *, output_ref) -> InputClosure
record_read(returned, *, tool, request, source_reference,
            actual_selector, input_dependencies) -> ReadReceipt
shared_projection(response, recipients, *, runtime, workspace_id,
                  current_scope) -> ProjectionResult
to_costorm_information(read_receipt, *, current_scope) -> Information
```

`ProjectionResult`는 `{status='AVAILABLE'|'BLOCKED_SCOPE'|'DEPENDENCY_UNVERIFIED',projection,dependency_ids,reason_code}`다. blocked이면 projection=null이며 title/claim/Plan 등 민감한 부분도 반환하지 않는다. 정상 projection은 원 응답의 전체 의존성을 유지한다. 도구/모델이 적은 source_refs를 authority로 읽지 않는다.

B의 `ActionLiteratureAccess`는 기존 성공 작업 journal 포맷/성공 자산을 확장·재사용한다. 별도 Literature owner/cache/store가 아니다. `public_access`는 모든 역할 및 진행자 SelectedRetriever에 같은 객체를 전달한다. 독립 Source/Corpus 읽기 기능과 현재 public topic-only gate를 보호한다.

B는 `ResultAccess`의 **scope/허가·tool dispatch 및 receipt 의존성**을 소유한다. 물리 selector 정규화·실제 retained reader/분석 engine 호출은 C가 제공하는 아래 인터페이스를 사용한다. 두 팀이 각각 같은 결과 validator/분석 함수를 복제하지 않는다.

### 10.6 C → B/root: exact 결과와 분석 callback

`caelab/research_team_results.py`:

```python
probe_retained_result(reference, *, resolve_document, verify_retention)
    -> VerifiedResultDescriptor
normalize_selection(descriptor, selection_request, *, granted_selector)
    -> CanonicalSelector
read_selected_result(reference, canonical_selector, *, readers, read_limits)
    -> ExactResultRead
prepare_analysis(request, *, scope, result_access, describe_inputs,
                 describe_resources) -> PreparedAnalysis
execute_prepared_analysis(prepared, *, existing_callback, execution_control)
    -> AnalysisReceipt
```

`VerifiedResultDescriptor`는 `{reference,descriptor,descriptor_digest,verified_storage_ref}`다. scope 판단 전에 숫자 선택을 읽지 않는 기존 retained owner 검증을 사용한다. `ExactResultRead`는 `{payload,receipt}`이고 receipt는 §9.2 형식이다. C가 확인하지 못한 native selector를 B가 문자열 비교만으로 허용하지 않는다.

`execute_prepared_analysis`는 현재 owner scope/입력 digest를 다시 확인한 한 번의 원 callback invocation이다. `PreparedAnalysis` 생성만으로 실행하지 않는다. 승인 없는 모델 request dict를 이 함수의 prepared 인자로 사용할 수 없다. root의 `_create_assistance` 또는 기존 owner callback 조립에서 원 result/analyze callback을 **호출별 factory에 캡처**해 제공한다. 전역 callbacks를 임시 바꾸지 않는다. 새로운 public operation 이름을 등록하지 않는다.

`caelab/research_team_followup.py`:

```python
proposal_origin(discussion, turn_id, proposal_index) -> dict
plan_link(origin, plan_document) -> dict
result_review_draft(discussion, *, plan_link, result_reference,
                    selector, current_scope) -> dict
study_proposal(discussion, selected_claim_ids) -> dict
```

반환은 기존 문서의 제안/초안/참조다. source claim/response 전체 생성 의존성을 누락하지 않는다. Plan 실행, 새 Ask, Study 채택을 자동 수행하지 않는다.

### 10.7 D — Qt·Report·portable

`apps/research/research_team_panel.py`는 기존 창용 presenter/helper다. §7의 실제 팀/논점/발언/자료·결과 선택, 미완료 과제, 응답 완료/지도 pending, 명시 retry/다음 phase를 연결한다. 기존 source picker/result preview/plan opener/worker/소유 창 종료를 재사용한다.

필요한 전용 closure helper는 `caelab/portable_research_team.py`에 둔다. `collect_team_closure`, `project_archived_team`, `validate_current_team_view`만 기존 portable_research_knowledge/owner가 호출한다. 새 store/ACL 또는 원 source 전체 탐색은 없다. 원 archive/read 권한과 현지 새 Ask/완료 응답 수집을 구별한다.

Report의 snapshot 생성/원문 읽기/내보내기는 B의 전체 생성 의존성 검사를 사용한다. D가 별도 문장 필터나 독자적인 공개 판단을 만들지 않는다. root는 기존 `_public`/원 응답 읽기에서 v2의 현재 view 검사를 호출한다. 허용된 local 원문 facet과 recipient-safe shared facet을 구별하며, raw private response가 일반 직렬화 payload나 cached preview로 우회 노출되지 않게 한다. 지도 stale/blocked일 때도 현재 허용된 개별 원 발언을 볼 수 있어야 한다.

### 10.8 root-only 공유 파일 접점

| 공유 파일 / 실제 접점 | 최소 수정 | 보호 |
|---|---|---|
| `assist/experts.py::_Budget.reserve_provider_steps` | trusted `_allocation` 분기, root/slice 원자적 예약 | `_allocation=None` legacy 예약식·default·미사용분 비환불 |
| `assist/experts.py::_run_approved_role/_ask` | `_binding` keyword, role별 준비·입력 계측·실제 도구 permit·repair 분기·generated_jobs 제한 | 기존 도구 engine/정상 ask·model override 권한 제한 |
| `assist/costorm.py::run/SelectedRetriever` | trusted v2 위임, 선택적 `public_access` injection | 최신 public topic-only/results-only·archive/locator·검색 journal |
| `discussion_document.py::diagnostics/_public/_arguments/_submit_next/_collect/command/_recover_evaluations` | v2 validation/delegation·checkpoint 수집 | 기존 owner/CAS/receipt·빈 progression arguments·copied/live 구별 |
| `discussion_costorm.py::start_record/arguments/authorize/collect` | v2 phase/predecessor·trusted factory·원 role response/Plan 보존 | 일반 Co-STORM 최신 start 관문·원 retry·원 보고서 보존 |
| `workbench.py`의 assistance/result/analyze callback 조립 | C의 기존 reader/원 analyze callback을 호출별 binding factory로 전달 | retained owner fallback·resource/native binding·FN05/Data |
| 기존 Expert/Study/Report/Reference GUI | D helper 위임과 source/result 선택 연결 | 한국어/dirty/Undo/CAS/late selection/창 수명 |
| `portable_research_knowledge/owner`, 관련 Report closure | v2 선언적 의존성/pending 수집 | 원 A/원 submitted hash·원 session 비복제·현지 새 Ask |
| `assist/_vendor/costorm/*`, `openscience_host.py`와 Windows helper | 원칙상 변경 0 | pin/notice/license·소유 process cleanup·구독 경로 |

표에 적힌 현재 원 함수/동작은 첨부 검토와 앞선 확인 자료에 근거한다. root는 현재 main/WIP의 해당 본문에 좁은 hunk를 적용한다. 파일 전체를 이전 baseline으로 교체하라는 계약이 아니다.

## 11. 네 개의 병렬 개발 묶음

이 절의 A/B/C/D는 실제 구현 책임이다. 문서 안의 helper 목록을 각각 별도 과제로 쪼개지 않는다. 하나의 사용자 연구 chain을 공동 인터페이스로 나눈다. Pro는 설계·중요 판단, Sol 담당은 큰 묶음 구현, Astra는 독립 검토, root/Codex는 공통 통합·Git/Space·실제 Windows 연결을 맡는다. 다른 완성 제품의 통합·게시는 계속한다.

| 묶음 | 전용 작성 파일 | root에 넘길 공유 hunk | 사용자 관점 종료조건 |
|---|---|---|---|
| **A runtime/owner/contract** | `research_team_contract.py`, `discussion_research_team.py`, `assist/research_team.py`, `assist/research_team_map.py`, 연구 역할 예제·관련 tests/runnable | `_Budget` allocation, `_ask` binding과 입력/repair 지점, costorm v2 분기, Discussion authorize/collect | 기본4·선택8 안에서 3역할 실제 조사→대상 질문→근거 답변/수정이 유한 advance로 완료. role 완료와 map failure가 분리되고 완료 actor 재호출0 |
| **B 자료/검색/투영** | `assist/research_evidence.py`, action Literature helper, 실제 분야 source manifests와 검색/의존성 tests | 실제 입력 계측 소비, guarded tool permit, SelectedRetriever public_access injection, source/Report current checks | exact revision/locator·읽기 수준·적용성을 확인. 제한 내용을 무인용으로 바꿔도 공유 차단. 공개 자료만의 정상 조사/공유와 search 성공→read 실패 복구 동작 |
| **C Plan/실제결과/Study** | `research_team_results.py`, `research_team_followup.py`, 실제 기존 reader/analysis/Plan chain tests와 공개 예제 | 기존 result/analyze callback factory, Plan·Study·후속 phase의 최소 연결 | 허용 exact 결과·분석은 실제 사용, 범위 밖은 payload reader/_execute0. 제안→명시 실행→실제 결과→같은 연구 후속 판단·Study 저장까지 완결 |
| **D Qt/Report/portable** | `apps/research/research_team_panel.py`, 필요 시 `portable_research_team.py`, UI/closure/cold 예제·tests | 기존 창 helper 연결, R1/P2 current dependency 검사, portable v2 closure | 실제 메뉴로 연구·개입·남은 과제·지도 retry·계획/결과/Study/Report를 조작. 원 store/provider 없는 두 process cold/재복사와 현지 새 Ask 분리 |

### 11.1 선행관계와 조립 순서

이 문서의 v2 자료형/함수 계약으로 네 묶음을 동시에 작성한다. A 런타임 전체가 끝날 때까지 B/C/D 작성을 대기시키지 않는다. B/C의 작은 positive fixture와 D presenter는 공통 계약대로 독립 검증할 수 있다.

통합 검증의 순서는 **A 계약+원 budget hook → B 입력 의존성과 C exact reader/analysis factory → A 실제 역할/Co-STORM pending transaction → C Plan·실제 결과 환류 → D Windows/Report/portable 전체 chain**이다. B의 공개검색 기존 성과는 독립적으로 유지하며 이를 새로 구현하기 위해 되돌리지 않는다.

### 11.2 교차 책임을 한 곳으로 고정한다

A는 언제 누구를 호출하는지와 owner checkpoint/budget/map transaction을 소유한다. B는 실제 공급 입력의 의존성·수신자 공유·공개검색 scope와 공동 journal을 소유한다. C는 실제 결과의 물리적 selector 의미·기존 owner 검증/reader와 기존 analyze/Plan 실행 연결을 소유한다. D는 이 기록을 정상 Qt 조작·Report/portable 경계로 소비한다.

공통 `experts.py`, `costorm.py`, `discussion_document.py`, `workbench.py`, `expert_window.py`, portable 파일의 최종 작성·충돌 해결은 root 소유다. 담당자는 해당 함수의 최소 hunk와 전용 source를 전달한다. 공유 전체본 덮어쓰기나 중복 validator·새 일반 authority layer는 없다.

### 11.3 각 묶음의 인도 범위

각 묶음은 전용 제품 소스, 관련 tests, 공개 runnable, 실제 실행 로그와 NOT_RUN, 짧은 한국어 조작법, root-only integration hunk를 반환한다. 소스 없이 함수 이름/미지원 표만으로 완료 처리하지 않는다. 이번 Pro 요청 자체의 산출물은 이 설계 MD이며 구현 ZIP 인도 요청으로 바꾸지 않는다.

Astra는 특히 budget reserve·자동 주입 의존성·같은 run의 다른 selector·공개검색 상한·분석 gate·실제 KB 부분 삽입 실패를 독립 검토한다. root는 파일 수/호출 수보다 사용자 chain과 참조 의미를 확인한다. 기존 완성 B/피로 C/Post/Numerical/portable 통합을 중단할 이유는 없다.

## 12. 수용시험과 완료를 주장할 수 있는 범위

### 12.1 서로 다른 다섯 판정

설계 채택, 제품 구현, controlled 계약 검사, 실제 구독/검색/Windows 실행, 공학 적합성은 별개다. 이 문서는 첫 번째에 사용할 계약을 확정한 것이다. 나머지 실행을 수행했다고 주장하지 않는다.

| 검사층 | 실제 검사 내용 | 그 결과로 주장하지 않는 것 |
|---|---|---|
| controlled | 실제 X/JobManager, 실제 `_Budget.reserve_provider_steps`, 실제 vendored step/KB와 명시 generation/I/O double | 실제 AI 연구 품질·실제 provider 또는 검색 성공 |
| 실제 검색·읽기 | 기존 BM25/KnowledgeStore와 실제 보존 원문, 허용된 live Crossref/read를 별도 수행 | 모든 분야 지식·논문 이해 또는 현재 부품 적합성 |
| 기존 구독의 실제 팀 | 회사 자료 없이 공개 질문/자료로 역할별 도구 사용·상호질문·수정 | 공학 자격, 모델 응답의 독립성 또는 자동 승인 |
| Windows Qt/native | 실제 통합 소스와 기존 설치 FreeCAD/Gmsh/solver/ParaView, 입력·선택·환류·창 수명 | 전체 solver 캠페인 또는 모든 기능 수용 |
| 사용자 공학 판단 | 실제 조건/시험/허용기준·근거에 따른 판단 | 앞 네 층의 단순 성공 수로 대체 불가 |

추가비용0은 무제한 호출이 아니다. 현재 사용권 한도에서 멈추며 새 API/크레딧/계정/provider fallback을 쓰지 않는다. 미실행, 실패, timeout, 일부 성공을 별도 기록한다. 이전 portable 테스트 수·호스트 답변 1개를 이번 연구팀 시험으로 합산하지 않는다.

### 12.2 기존 RT01–20의 강화된 완료 조건

| ID | 수행할 사용자/반례 | 최소 종료조건 |
|---|---|---|
| RT01 | 주제만/자료 없음/모델 미설정 | 문제정의·필요자료·수동 편집/Undo/save 가능. inference/search 자동0 |
| RT02 | 3 investigator, 같은 model, 서로 다른 task/tool/source | 실제 actor session과 생성 입력/실제 read 기록. default4 첫 action에서 R1/R2만 실행; R3에 다른 역할 결론 전달0 |
| RT03 | 초기 조사 barrier 뒤 특정 claim 질문·답변/수정 | §4.5의 4는 3 actions, 8은 2 actions 정상 fixture. 완료 초기 역할 재호출0, 무한 advance/고정 독백으로 통과 불가 |
| RT04 | 가짜 locator·결과 수치·형식 오류 | 원 response 보존, invalid/unknown 표시, repair는 배정된 1 step 안. 없는 evidence 생성0 |
| RT05 | 공개+제한 입력을 읽은 A가 무인용 가설/질문/수정 이유 출력 | 좁은 B·진행자·shared history/KB/Report/portable preview로 전체 응답 누출0. 모델 source_refs가 빈 경우도 동일 |
| RT06 | 같은 제목 다른 revision·중간 revoke·변경 후 cached retry | 원 정확 개정/bytes 보존. 현재 projection/cache/model/retry/export에 동일 차단. 허용 frozen과 scope 거부 구별 |
| RT07 | 실제 BM25/source와 잘못된 solver 버전 자료 | 실제 locator·읽기 수준·버전/적용성 표시. 높은 검색 score를 적합성으로 승격0 |
| RT08 | 역할 2+진행자에서 public query 시도, 허가/비허가 | 논리 action 합산 실제 search≤2, 각≤4paper. 세 번째 외부 search0. 직접 literature tool과 retriever가 같은 ledger 사용 |
| RT09 | search 성공·일부 read 성공·나머지 read 실패, archive 변조 | retry의 search0/성공 read0. 실패 read만 현재 허가로 수행. 성공 순위/원 archive/locator 유지 |
| RT10 | 실제 root reserve + BudgetSlice, 4/8/1, consult/repair/map | 어떤 actor도 root/자기/보호 몫 초과0. provider 예약 미사용분 환불0. 도구 뒤 응답 여유 없는 task 시작0 |
| RT11 | 실제 upstream step 역할 성공 후 첫/부분 KB 삽입 실패 | 원 role/Plan/receipt 즉시 읽힘. retry generate_utterance0/step0, duplicate durable turn·인용·KB항목0, 원 response 인용 bytes 불변 |
| RT12 | map budget 소진/취소·pause·개입·late reply | 임시 KB만 폐기, 승인 snapshot 불변. 현재 buffer 보존. 다음 역할 정지, 원 제출 prompt 재작성0 |
| RT13 | checkpoint/role/map commit 응답 유실·generation 경합 | 같은 command 재확인의 신규 host/search/analysis/map0. 완료 task/pending idempotent. 현재 편집 덮어쓰기0 |
| RT14 | analyze scope 없음/넓은 operator만/초과/모델 합성 table | 모든 거부에서 `_execute=0`. 정상 exact scope는 기존 analyze 실제 1회. 성공 응답 재확인의 추가 실행0 |
| RT15 | 같은 run의 다른 component/leaf/time/행, tampered hash | 숫자 payload reader 전 거절. 허용 부분집합은 정상 read. 다른 단위/측도/metadata fallback 거절. 실제 부분 결과는 원 범위로 표시 |
| RT16 | 실제 Plan 실행·후속 결과·Study/Report | 원 claim/판별 조건에 실제 result/selector가 연결. 명시 판단 Apply/Undo/save. 수치 성공으로 release 변경0 |
| RT17 | legacy sequential/Co-STORM와 v1/v2 공존 | 최신 legacy public topic-only/results-only 정상 시작. selected_sources 필수 재도입0. v1 원 실행 자동 승격0 |
| RT18 | 원 READY/RUNNING/dispatch_pending/map pending 복사 | 원 기록/의존성 보존, 현지 원 job lookup/harvest/retry/자동 dispatch0 |
| RT19 | 첫 cold→편집·현지 새 Ask→재복사→두 번째 cold | 원 store/provider/session 없이 허용 원문/토론/편집 읽기. 새 local job 완료 수집/같은 command 확인만 가능 |
| RT20 | 실제 Windows 한글/공백·좁은 창·취소·다중 창·닫기 | 정상 메뉴로 업무 A/B chain 조작, buffer 손실0, 소유 process/window만 종료 |

### 12.3 네 핵심 계약을 위한 추가 반례

| ID | 구체 경계 | 필수 관측 |
|---|---|---|
| RT21 | 자동 snippets만 제한 내용을 주입하고 모델 citation은 공백 | 모델이 직접 source tool을 안 써도 dependency가 role 전체에 붙고 shared 차단 |
| RT22 | 제한 session history 또는 consultation이 공개 source 응답에 섞임 | response 전체가 제한에 결속. 다른 actor로 session ID 재사용 불가. 깨끗한 별도 public task/session은 정상 공유 |
| RT23 | 허용 X@A/Y@B에서 X@B 요청, 시간 같은 다른 frame, reader 중간 변조 | 필드별 union 확대0. 원 frame/row identity 유지, 검증/읽기 사이 변경 탐지, 위반 payload 전송0 |
| RT24 | SelectedRetriever 한 호출 실패 후 새 호출·직접 tool·명시 retry 혼합 | 같은 논리 action에서 성공분/journal/2회 상한 유지. 실패/취소 search도 시도 몫 소비. cache hit는 network0 |
| RT25 | map 임시 snapshot 일부 변경 후 실패·첫 commit 직후 유실응답 | 과거 active map 변경0/원 role bytes 변경0. retry는 동일 base에서 성공 prefix replay, 한 pending 한 번만 APPLIED |
| RT26 | pending 또는 이미 승인한 KB 근거 revoke | pending 삽입0. 오염된 현재 KB/Report view 차단. 허용 개별 응답 읽기 유지. 깨끗한 새 map은 제한 base/journal을 안 씀 |
| RT27 | analysis 자원·행/열/byte/응답/options 범위 초과 및 valid 입력 | 전자는 resolve/실행 순서상 가능한 가장 이른 단계 거절·_execute0, 후자는 기존 수학 실제 실행·원행/실패행 provenance 보존 |
| RT28 | 같은 action partial의 FINALIZE/REPAIR, budget1/짧은 deadline | 완료 tool/search/역할 재호출0. 충분한 명시 예산에서 미완료 답변만 실행, 부족하면 대기; 구조 교정은 실제 조사 재실행이 아님 |

RT02/03/10의 기록에는 각 action의 한도, ticket 배정, root reserve의 반환 steps, 실제 observed host/tool 횟수, 완료/미완료 task ID, 초기 역할에 보낸 입력 목록이 있어야 한다. 이를 “예산 object가 mock에서 통과했다”로 대신하지 않는다.

RT11/12/25의 map 시험은 실제 pinned step과 실제 `KnowledgeBase.update_from_conv_turn`을 사용하고, 생성/외부 I/O 경계만 controlled double로 둔다. map 함수를 빈 stub으로 바꿔 원응답 보존만 검사하지 않는다. 예산 소진·취소를 각각 별도 fault point로 주입한다.

### 12.4 공개 runnable 두 개와 전체 종료조건

`examples/research_team_cause_public.py`: 공개/자체 작성 작은 문헌·합성 관측을 표시하고, 현재 지원 backend의 실제 명시 계산 또는 보존 result를 사용한다. 연구→계획→실제 결과→가설 후속검토→Study/Report→cold를 재현한다. 낙하 동해석을 실제 실행하지 않았으면 그 물리해석을 수행했다고 표시하지 않는다.

`examples/research_team_fixture_public.py`: 편집 가능한 공개 FreeCAD 지그·작은 조립을 기존 입력/메시/solver/Post 경로로 검토하고 정확 결과와 반론을 같은 연구에 연결한다. Windows/native 미설치에서는 해당 단계 NOT_RUN을 유지하며 headless controlled를 실제 native 성공으로 세지 않는다.

두 runnable은 기본적으로 provider 자동 호출0이다. controlled mode와 현재 기존 구독을 명시 사용하는 mode를 분리한다. 자신의 임시 폴더/process/job/window만 생성·정리하며 원 사용자 자료/fixture/store는 삭제하지 않는다. 두 cold process의 별도 identity와 원 source 차단, 실제 dispatch counters를 기록한다.

전체 사용자 종료조건은 **역할의 실제 조사 → 대상 질문/근거 답변 또는 수정 → 필요한 시험/계산 계획 → 명시 기존 실행 → 실제 결과 후속 토론 → 사용자 Study/Report 편집 → 저장·재열기**다. 근거 부족으로 UNKNOWN을 남기는 것은 유효한 결과지만, 조작/연결이 없는 상태를 근거 부족이라는 말로 완료 처리하지 않는다. RT 핵심 반례와 두 업무 chain을 실제 확인하기 전에는 “실제 전문가 연구팀 완성”으로 표시하지 않는다.

## 13. 선택 이유와 버린 대안

| 대안 | 판단 |
|---|---|
| 이름과 system prompt만 6~8개 추가 | 부족. 실제 역할별 조사·근거·대상 질문·수정·계산 환류를 구현하지 못함 |
| 현재 sequential을 전부 제거 | 불필요. 실제 역할 runtime과 owner/권한을 이미 사용함. 독립 조사의 실행과 legacy 가벼운 자문 경로로 보존 |
| Co-STORM Completion에 도구 map만 꽂기 | 부족하고 위험. upstream component가 곧 승인된 specialist가 아니며 도구/세션/출처 귀속·공유 budget·계산허가가 해결되지 않음 |
| 여섯 Co-STORM component마다 다른 모델을 지정 | 모델 분산일 뿐 역할별 조사 계약을 대체하지 않음. 같은 모델도 사용할 수 있고 현 비용/접근 조건에서 필수 아님 |
| Co-STORM을 보고서 렌더러로만 축소 | 선택하지 않음. 실제 진행 정책·moderator의 근거 기반 질문·논점 지도까지 재사용. 담당자의 실제 실행은 ExpertRuntime adapter |
| OpenScience 자체 lead/worker에 팀·파일·실행 전체 위임 | 이번에는 선택하지 않음. 기존 X/N/권한·job/portable를 우회하는 두 번째 orchestration이 생김. 현재 CAE tools를 가진 제한 호스트로 재사용 |
| LangGraph/AutoGen/CrewAI 등 새 프레임워크 도입 | 이번 요구에 필요 없음. 이것들이 원천적으로 불가능해서가 아니라 현재 owner/JobManager/Co-STORM/Runtime의 책임을 중복하기 때문 |
| 대규모 fine-tuning·새 embeddings/vector DB | 현재 병목은 이름/모델 능력보다 실제 자료·작업 연결/검증. 설치·자료·비용을 늘리고 이번 chain에 필수 아님 |
| 전원이 동일 collection 교집합만 조사 | 전문 역할의 자료를 불필요하게 버림. 역할별 조사와 recipient-safe 공유로 대체 |
| 전원의 source union을 공동 대화창에 전달 | source grants와 역할 경계 위반 가능. 요약을 통한 우회도 금지 |
| 과거 runner/session을 그대로 복사해 새 PC에서 resume | 원 job/session/권한 재사용 금지와 충돌. archive 읽기+현지 명시 새 Ask로 유지 |
| 다수결/자기평가 점수로 제작 승인 | 선택하지 않음. 상관된 모델 오류·미관측 조건·실제 시험 부재를 해결하지 못함 |

앞선 설계의 Co-STORM 대화·지도 재사용 선택을 유지한다. 공학 release authority를 모델이나 지도에 새로 주지 않고 실제 실행·사용자 판단을 기존 CAE 문서와 도구에 결속한다.[OLD]

추가로 다음 대안을 명시 폐기한다. 남은 root 예산을 먼저 예약한 뒤 역할별로 나누는 방식은 선점 문제를 고치지 못하므로 호출 전 ticket allocation을 택한다. 모델 citation만 검사하거나 문장 의미를 추정해 제한 내용을 잘라 내는 방식 대신 전체 입력 의존성·응답 단위 판정을 택한다. 도구 allowlist만 좁혀서 exact 선택/analysis scope를 구현했다고 보는 안 대신 실제 dispatch permit를 둔다. vendor 코드를 직접 수정하거나 map 실패 때 role을 재실행하는 안 대신 instance별 DeferredKnowledgeBase와 임시 snapshot transaction을 택한다. 기존 공개검색 성과를 무시하고 문헌 필수 관문을 복구하는 안은 버린다.

## 14. 통합 보호와 개발자에게 넘길 명령

이번 변경의 사용자 기능은 **기존 Expert 앱 안에서 범위를 확인한 전문 역할들이 실제 조사·상호검토하고, 기존 Plan/solver 결과를 받아 같은 연구를 계속하는 것**이다. 네 묶음은 이 chain의 충분한 부분을 완결해 인도한다. 작은 함수/지원표/모델 호출 1개로 묶음 완료를 선언하지 않는다.

각 담당은 자신에게 지정한 전용 제품 source/tests/docs/public runnable과 원 기준 대비 최소 integration hunk를 반환한다. 공유 전체 파일 대체·광역 정리·관계없는 코드 삭제는 하지 않는다. 요청의 main68c8b53과 root 최신 통합 변경이 다르면 소유한 접점에서 실제 본문을 대조하고 원 의미를 유지한다. 기준을 맞추기 위해 root의 통합을 되돌리거나 다른 Pro 작업을 중단시키지 않는다.

수용검사는 해당 boundary와 대표 chain으로 제한한다. 전체 과거 솔버 캠페인을 선행조건으로 반복하지 않는다. FN05/Data fit/holdout/측도/원 수학, B13/Contact/PDE/Impact의 병렬 core, Report R1/P2 원문/이미지·현재 navigation, Windows helper/한국어 UI, fixture/upstream pin·license/notice를 보호한다. CB04–08와 candidate/부분 opener/managed native의 잔여는 제거하거나 완료로 표시하지 않는다.

실제 source/patch/로그를 전달하지 못하면 해당 인도는 미전달이다. controlled execution, actual retrieval, subscription runtime, Windows/native, engineering qualification은 각각 구분해 기록한다. 이 설계 MD에는 실제 구현 ZIP·tests PASS·Git 게시가 포함되어 있지 않다.

### 14.1 이 교체본을 인계할 때의 공통 확인

root는 새 v2 action에서만 allocation/binding/DeferredKnowledgeBase 경로가 활성인지, 일반 mode의 최신 public topic-only/results-only가 유지되는지 먼저 확인한다. B가 공급한 입력 의존성과 C의 exact 결과/analysis factory 없이 A가 legacy callback으로 fallback하면 통합 불가다. 반대로 정상 허용 자료·정확한 결과·분석을 일괄 차단해도 통합 완료가 아니다.

네 묶음은 원 역할 응답·계획·receipt를 먼저 보존하는 action checkpoint와 원 sourcegrant 경계를 공통 기준으로 삼는다. 권한·예산·지도 상태를 새 ACL/workflow owner로 옮기지 않는다. 현재 main에 없는 다른 로컬 변경을 이미 확인했다고 말하지 않으며, 공통 hunk 적용은 root가 현재 본문과 대조한다.

## 15. 이번 입력·근거 및 변경 추적

### 15.1 실제 읽은 파일

| 구분 | 파일 | 사용 범위 |
|---|---|---|
| REQ | `correction-request.md` | 전체 25행. 현재 기준·다섯 수정사항·A/B/C/D 책임·무료/보호 조건 |
| REV | `REVIEW.md` | 전체 78행. Astra의 읽기 기준, 유지할 방향, 네 접합 결함과 최소 완료 조건 |
| OLD | `PRO-CAE-RESEARCH-TEAM-20261016-01.md` | 전체 742행. 기존 전체 구조·두 업무·Qt·Plan·portable·네 묶음·RT01–20·선택 이유 |

입력의 원 bytes는 수정하지 않았다. REQ/REV의 최신 소스 관찰은 root/Astra 제공 사실로 인용했으며 이번에 최신 소스 전체·로컬 WIP·다른 채팅을 읽었다고 간주하지 않았다. OLD의 당시 GitHub/외부 문서 확인 기록은 과거 기록이고, 이번 교체본에서 새로 수행한 조회/실험이 아니다.

### 15.2 문서 내 출처 표기

<a id="req0"></a>**REQ0** — correction-request.md 3–5행, 기존 방향 PASS 및 현재 main/pin/보호 변경.

<a id="req1"></a>**REQ1** — correction-request.md 7–8행, 실제 4/8 예산과 greedy reserve, 초기 독립성·이어가기 요구.

<a id="req2"></a>**REQ2** — correction-request.md 10–11행, 실제 전체 입력 의존성·응답 단위 결속.

<a id="req3"></a>**REQ3** — correction-request.md 13–16행, exact result/selector, 공동 literature journal, analysis gate와 trusted hook.

<a id="req4"></a>**REQ4** — correction-request.md 18–19행, 실제 upstream step/KB 변이와 분리 복구.

<a id="req5"></a>**REQ5** — correction-request.md 21–22행, 8dddcb2의 public topic-only/results-only 및 최신 보호 조건.

<a id="rev1"></a>**REV1** — REVIEW.md 19–29행, 실제 예산/초기 barrier 반례와 완료 조건.

<a id="rev2"></a>**REV2** — REVIEW.md 31–41행, 자동 snippets/history 등 전체 입력의 생성 의존성과 무인용 누출 반례.

<a id="rev3"></a>**REV3** — REVIEW.md 43–59행, job-ID 범위·public journal 우회·직접 analyze callback의 접합.

<a id="rev4"></a>**REV4** — REVIEW.md 61–71행, 무조건 KB 삽입·인용 문자열 변이·원 역할 완료 보존·retry.

<a id="old"></a>**OLD** — 앞선 전체 설계. §6 두 대표 업무, §7 Qt, §9 기존 문서·portable 연결, §11 네 묶음의 기능적 범위를 계승했다. 실행 계약에서 이 문서와 다른 예산/의존성/dispatch/지도/시작 규정은 본 R2로 대체한다.

[REQ0]: #req0
[REQ1]: #req1
[REQ2]: #req2
[REQ3]: #req3
[REQ4]: #req4
[REQ5]: #req5
[REV1]: #rev1
[REV2]: #rev2
[REV3]: #rev3
[REV4]: #rev4
[OLD]: #old

### 15.3 기존 절의 수정 지도

| 원 설계의 핵심 절 | 이번 최종 규정 |
|---|---|
| §2.2, §4.4 초기 조사/질문 순서 | §4.2 investigator barrier. 다른 역할 결론·KB를 초기 prompt에서 제외 |
| §4.5의 추상 budget view/runtime8 설명 | §4.3–4.5 실제 기본4/상한8·root 예약 allocation·ticket 비용·구체 action 일정 |
| §3.3/§5.3의 source refs/혼합문장 분리 | §3.4·§5.3–5.5 전체 공급 입력 manifest와 응답 전체 공유 판정. 문장별 축소 폐기 |
| §3.4/§9.1의 result/analyze 선언 | §9.2–9.4, §10.3–10.6 실제 dispatch permit·exact selector·명시 분석 실행 gate |
| §4.3/§8.3의 역할 완료/지도 retry 원칙 | §8.1–8.4 DeferredKnowledgeBase·임시 KB transaction·성공 journal replay |
| §8.5 legacy selected_sources 필수 | §8.5 최신 public topic-only/results-only 정상 시작 보호로 교체 |
| §10.2/10.3 함수/자료 계약 | §3·§10의 v2 자료형·binding·정확한 root hook |
| §11/§12 역할 분할과 수용시험 | §11 네 큰 묶음 유지, §12 RT01–20 강화 + 핵심 반례 RT21–28 |

최종 설계가 확정됐다는 사실과 제품 구현/실제 구독팀/실제 검색/Windows/native/공학 적합성이 확인됐다는 사실을 합치지 않는다. 이 문서에는 미실행 결과를 PASS로 기록하지 않는다.
