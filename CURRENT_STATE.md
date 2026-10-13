# 현재 작업과 제품 상태

갱신: 2026-10-13. 이 파일이 현재 사실·맡긴 작업·다음 행동의 유일한 원본이다.
제품 목표는 [PRODUCT_PLAN](docs/PRODUCT_PLAN.md), 상세 기능은
[PRODUCT_UI_MCP_PLAN](docs/PRODUCT_UI_MCP_PLAN.md), 역할·갱신 규칙은
[CODEX_WORKFLOW](docs/CODEX_WORKFLOW.md)를 따른다.

## 현재 통합 중인 변경

Expert 연결 코드와 교정을 로컬 main `4a952f5`까지 통합했다. 아직 원격에
게시하지 않았다. 기존 원격 main은 `6f676f4`다. 연결/UI/config 검사 12개와 host 관련
7개는 통과했고 실제 `install-windows.ps1 -ResearchUI`의 Expert/MCP import도 통과했다.
설정 적용 후 세 번째 실행에서 기존 서비스를 다시 찾지 못하던 문제는 Pro의 UTF-8
읽기·쓰기 교정으로 해결했다. 실제 Windows에서 적용 후 재실행, 옛 BOM 없는 파일,
저장 설정과 실행 중 설정 불일치 검사 3개가 통과했다. 이어 역할 상세 UI를 통합했으며
처음 6개 UI 검사 중 초기 역할 조회 1개가 실패했다. 자동 문서 조회와 역할 조회가
겹치면 초기 요청이 사라지던 문제는 Pro 요청 `EXPERT-INITIAL-ROLES-03`의 `167da66`으로
교정했다. 기존 worker가 바쁜 동안 역할 조회 의도를 유지하고, 명시적 저장/질문 후속
작업이 끝난 뒤 중복 없이 읽는다. 로컬에서 초기 polling 경합과 명시적 후속 작업 검사가
각각 통과했다(2개, 5.93초). 대기 시간을 늘리거나 모델 호출을 추가하지 않았다.

사용자는 화면의 `Use existing OpenScience subscription profile` 문구가 OpenScience
자체 구독을 요구하는 것처럼 보인다고 지적했다. 실제 표시는 `기존 OpenScience 설정 사용`으로
바꾸고 AI 제공자 로그인/이용권과 분리한다. 화면에 보인 두 역할은
`examples/workbench_experts.json`의 예시 지시·자료 분류·도구 설정이다. 분야별 학습,
전문 자료집 구축 또는 전문성 평가를 완료한 모델이 아니다. 예시 역할의 실제 구성과
준비 상태를 확인할 수 있게 하며, 이름만으로 전문성 또는 추론 가능 상태를 주장하지 않는다.

Pro 후속 요청 `EXPERT-WINDOWS-UX-02` 회수·통합 완료: 같은
[Pro 대화](https://chatgpt.com/c/6accef3a-e650-83ee-89e2-3f48a60dd17a),
Pro 제출 `81aa048`·`392fa76`, 로컬 통합 `a72fed0`·`2a35104`. Windows 경로 읽기 오류와
위 사용자 피드백을 같은 기존 브랜치에서 교정했다. Codex가 관련 검사·화면을 확인했다.
E5의 첫 실제 질문은 기존 OAuth 로그인과 `openai-codex/gpt-6-astra`로 응답을 받았다.
저장된 `runs/product-development/20261013/expert-live-round-01/result.json`은
ANSWERED / 40.359초 / 실제 host 호출 1회다. 회사 자료·외부 자료·계산은 사용하지 않았다.
질문은 단축 인장시험의 단위·단면적·변위 계측이 미확인일 때 피팅 전 필요한 정보를 묻는다.
제품의 실제 Expert 서비스와 기존 로그인 경로를 호출했으며, 예시 역할의 전문성 평가나
GUI 질문·취소·재개 전체 완료를 뜻하지 않는다. 실행 보조 스크립트의 마지막 콘솔 출력은
Windows cp949 문자 오류로 실패했으나 그 전에 UTF-8 결과와 실제 세션 저장은 완료됐다.
E6의 실제 서비스 흐름도 진행했다. AI가 `calculations.plan`으로 만든 제안을 기존
Numerical 문서로 열어 E=1000→1500 MPa로 수정하고 FELUPE 계산을 실행했다. 선택 결과를
원 논의에 첨부·전송 허용한 후 같은 AI가 `results.read`를 호출해 실제 응력과 조건 차이를
설명했다. 원 논의 4개 발언과 계산 1개를 저장하고 새 프로세스의 Qt 창에서 다시 열었다.
근거는 `runs/product-development/20261013/expert-plan-live-01/continued-result.json`과
`reopen.json`이다. 첫 보조 스크립트는 계산 뒤 저장을 빠뜨려 결과 참조 요청이 거절됐으며,
기존 저장 명령으로 이어 진행했다. 모델·계산을 다시 수행하거나 거절 조건을 변경하지 않았다.
이는 실제 OAuth/도구/계산/문서 저장 경로와 offscreen Qt 재열기 확인이며 OS 마우스
조작, 취소/재개, Study 전체 수용은 남아 있다. MoAI t2를 완료 처리하지 않는다.

## 지금 받을 수 있는 것과 인도 계획

2026-10-13 저녁 기준 제품 코드는 `b1a2aa9`까지 원격 main에 반영됐다. 한국어 안내·예제 수정·인도 계획은 `fbf37b3`으로 원격 main에 게시하고 같은 SHA를 확인했다. 아래 표가 현행 순서이며 뒤의 날짜별 서술은 기존 근거다.

**첫 사용본 목표는 10월 14일 오전 출근 전**이다. 한국어 설치·사용 안내를 따라
기존 CAD 예제를 열어 치수를 바꾸고 저장하거나, CAD 없이 포함된 수치 예제로 결과 파일을
만드는 범위다. AI 토론·전체 자동 해석을 이 첫 사용본의 완성 기능으로 광고하지 않는다.
README, 별도 설치법·사용법을 작성하고 humanize-korean Fast 윤문과 명령 대조를 마쳤다.
수치 예제는 10.64초에 끝났고 피팅 그림과 8개 결과 폴더·summary/result.json을 생성했다.
D1은 이 실행 범위로 게시 완료했다. 사용자 PC에서의 확인은 아직이다.

### 끝낼 단위와 예상 기간

Codex가 책임지는 최초 개발 견적이다. 작업일은 실제 구현·검토·통합에 쓰는 날이며,
대기 시간까지 측정한 확정 납기와 다르다. D2·D3 첫 인도 결과로 후속 견적을 보정하되
변경 이유·남은 작업·새 날짜를 먼저 기록한다. 전체를 끝내기 전에 각 인도본을 사용할 수 있게 낸다.

| 인도 | 사용자가 끝낼 일 | 현재 상태 / 바로 남은 작업 | 목표 또는 남은 작업일 |
|---|---|---|---|
| D1 첫 사용본 | 설치→독립 창 실행, 공개 CAD 치수 변경/저장 또는 실제 수치 예제→결과 파일 | 진입 기능 확인, 한국어 안내·실제 수치 예제 재현 완료. 게시 완료 | 10/13 인도, 10/14 사용 가능 범위 |
| D2 설계와 해석 | CAD 치수·조립/자세·재료·하중·접촉→메시→Runner→Post→변수 후보 계산→새 편집 설계 채택 | 기존 native 계산·후보 기능 있음. 새 저장 표현 확인, 실제 화면의 왕복과 실패/취소·참조 복구 인도 | 첫 지원 경로 10/16 목표, 넓은 명세 잔여 3–5일 |
| D3 연구 토론 | 기존 구독 연결→자료/질문→실제 전문가 토론→Plan 편집→계산 결과로 후속 논의·Study 저장 | Pro가 SPEC-EXPERT-002 구현 중. E1–E6을 고정한 작업표로 회수·검토·Windows 실행 | 10/15 목표, 인증/사용 한도 지연은 별도 보고 |
| D4 후처리 | 외부 결과 열기→필드·위치·시각 선택→측정·서로 다른 결과 비교→저장·재열기 | 기존 reader/측정 재사용. 비교 입력·오류 복구·native 화면 흐름 완성 | D2 이후 2–3일 |
| D5 데이터와 재료 | 시험 파일 열/단위 지정→구간 선택→지원 법칙 피팅→잔차/holdout 비교→계수 채택·저장 | 기존 Data/Material/fit 재사용. 각 조작과 데이터 전달의 누락 보완 | 3–5일 |
| D6 수치 연구 | DOE·최적화·역해석·UQ·대리모델·다목적 각각 계획 편집→실제 계산→결과 해석·채택 | 기존 엔진/Plan 있음. 방법별 화면, 중단/재개, 실패 후보, domain 채택 완성 | 3–5일 |
| D7 방정식·구성식·연성 | CAD 없이 식·영역·조건→실제 해/기준 비교, 구성식 상태·접선, 단계 간 장 전달 | 기존 지원 adapter 있음. FN-08/18/19의 명세별 미지원 조합·계산 연결 보완 | 4–7일 |
| D8 충격·손상 | 초기조건·접촉 지정→explicit 실행→에너지/힘/시간 결과 확인; 파괴·계면·피로 지원 경로 | explicit 제품 흐름 미확인. 기존 OpenRadioss/손상 관련 자산 조사 후 adapter·화면 연결 | 4–7일, 불확실성 큼 |
| D9 실험과 보고 | 측정·교정·시편 조건→예측/관측 비교→다음 시험·보고서 저장 | 파일 기반 기존 자료 재사용. 실제 장비 연결은 장비·권한·공개 자료가 있는 범위에서 별도 확인 | 소프트웨어 3–5일, 실제 장비 일정은 미확정 |
| D10 배포와 전체 연결 | 각 독립 도구 설치·재실행, 파일 이동·복구, 선택 Workbench와 GUI/CLI/Python/MCP, 외부 batch/SSH 경로 | 기존 launcher/owner/MCP 재사용. 지원표 확정·통합·배포 안내·새 환경 확인 | 3–5일 |

후속 D2–D10의 최초 합산 견적은 **27–45 작업일**이다(D3 2–3일 포함, 병행 단축 미반영).
이는 전체 연구 소프트웨어 지원 범위를 구현하는 초기 견적이며 실제 장비 실험·물리적 승인
일정을 뜻하지 않는다. 무료 실행 경로가 확인되지 않은 조합은 해당 인도에 미해결로 남기고
다른 조합의 완료로 대체하지 않는다. FN-01–35/기존 74작업은 아래와 같이 전부 연결한다.
D1은 기존 기능을 먼저 쓰기 위한 인도이며 전체 공통 설치 요구를 대신하지 않는다.

[74개 세부 작업표](docs/design/20261012-desktop-planning/pro-ux/implementation_map.csv)의
`delivery_id`가 각 작업을 위 인도에 연결한다. 기존 `implementation_status`는 기획 당시
상태이므로 현재 제품 완료 수로 집계하지 않는다. 각 행의 입력·구현 위치·의존·완료 조건을
유지한다. 새 기능 아이디어는 현재 인도의 성공을 막는 결함이 아니면 후속 항목으로 분리한다.
D2의 10/16 목표는 첫 접촉·후보 왕복이며 조립·비선형 전체 15개 세부 작업의 완료 날짜가 아니다.
D3의 E1–E6 뒤에는 독립 Study의 가설·판단·후속 연구(FN-29) 수용이 남는다.
D10에 연결한 공통 저장·충돌·동일 문서 유지 요구도 각 앞선 인도의 해당 조작에서 확인한다.
모든 인도는 실제 조작·계산/결과·저장/재열기·해당 실패 복구·사용 안내를 갖춰야 완료다.
개별 수치 정확성 검증과 실제 장비/공학 승인은 별도로 표시한다.

### 이번 배정과 MoAI 적용

- Codex: D1 문서·재현·게시와 현황 관리. MoAI `todo` t1에 등록하고 게시 후 완료 처리했다.
- 실제 Pro: D3 연결 제품 코드·관련 검사. MoAI t2와
  [E1–E6 구현 작업](.moai/specs/SPEC-EXPERT-002/tasks.md)에 연결한다.
  Pro가 기존 서비스를 안전하게 다시 읽는 적용 경로를 `eab4216`으로 게시했다.
  현재 Astra가 해당 제품 변경을 검토 중이며 main 통합·Windows 확인은 아직이다.
- Astra: 핵심 연결·권한·사용 흐름 독립 검토. Sol: 한국어 안내의 사실 보존 윤문.
  Luna: 기존 예제 실제 실행과 브랜치 현황 조사. 같은 파일의 동시 작성은 하지 않는다.
- MoAI MCP `spec_progress`, `spec_audit`, `spec_drift`, `todo_list`를 실제 호출했다.
  audit/drift는 lifecycle 검사이며 코드·명세 전체 의미 일치를 증명하지 않는다.
  CLI spec view는 현재 문서의 기준 항목을 추출하지 못했다. 이 기능의 연결은 미완료이며
  사람이 읽는 tasks/acceptance와 실행 근거를 완료 판정에 사용한다.
  8개 SPEC 중 7개가 progress 파일 부재로 legacy로 분류됐고 기존 todo는 비어 있었다.
  과거에 전체 MoAI 구현 절차가 실행됐다고 소급 표시하지 않는다.
- 설치된 MoAI run의 기존 코드 분석·동작 보존·수정·관련 검사 절차를 현재 Pro 작업에 적용하고,
  sync의 명세/실제 변경 대조·문서 갱신·게시를 Codex가 수행한다. 전용 manager-develop은
  현재 Codex agent catalog에 없으므로 실행했다고 주장하지 않는다. 지정된 Pro 작성자와
  Astra 검토를 유지하며 유료 모델 연결·전수 재검증을 추가하지 않는다.

### 작업 공간 정리와 새 실행 확인

브랜치 조사 당시 원격 25개(main 포함), 로컬 14개, 등록 worktree 13개였다. main에
완전히 포함되고 worktree가 없는 `codex/ui-interaction-design-20261010`,
`codex/workbench-local-integration`, `redesign/research-workbench-20261007` 원격 브랜치를
삭제했고 앞의 두 로컬 브랜치도 정리했다. 따라서 원격 22개·로컬 12개가 남는다.
Pro의 Expert/CAD 브랜치, 미반영 source와 로컬 변경이 있는 worktree는 보존했다.
`runs` 약 23.5 GB에는 실행 도구·설치물·계산 근거가 섞여 있어 일괄 삭제하지 않았다.

실제 첫 사용 예제에서 현재 private runtime의 matplotlib 누락을 발견했다.
기존 `install-windows.ps1 -ResearchUI`가 지정 의존성을 복구하고 import 검사를 통과했다.
기본 설치 명세 자체에서 빠진 패키지는 아니었다. 이어 예제의 batch 결과에 exchange_id가
빠진 결함을 찾아 Codex가 사용 안내 통합 범위에서 예제 한 줄을 고쳤다.
제품 importer의 정확한 입력 검사는 유지했다. 수정 후 실행은 exit 0 / 10.635초이며
피팅 그림·8개 결과 폴더·summary/result.json을 만들었다. 외부 교환 예제는 실제 결과 1개를
읽고 미계산 후보 1개를 미계산으로 유지했다. 상세 실행은
`runs/first-use-20261013-complete/run-receipt.json`이며 외부 solver/provider를 사용하지 않았다.

Luna의 실제 FreeCAD binary 저장/새 프로세스 재열기 검사는 새 저장본의 전체 형상·면
식별이 유지됨을 확인했다. 근거는 `runs/product-development/20261013/binary-shape-probe-01/result/receipt.json`.
과거 파일에 이미 저장된 낡은 접촉 참조를 고쳤다는 뜻은 아니며 solver를 다시 돌리지 않았다.

MoAI todo는 t1(D1), t2(D3), t3(D2), t4–t10(D4–D10)으로 등록했다.
이 목록은 CURRENT_STATE와 기존 작업표를 가리키며 별도 요구 범위를 만들지 않는다.
Astra는 74작업/35기능의 인도 연결과 explicit·손상·HPC·실험 범위 보존을 확인했다.
D2 첫 지원 경로와 전체 수용, D3 독립 Study 잔여, 모든 인도의 공통 저장 요구를 구별하도록 교정했다.

### 요구 52항목의 실제 상태

코드·현황·요구 효력·상세 작업표를 대조한 2026-10-13 감사다. **부분 구현 29,
미착수·미확인 3, 개발·운영·조사·역사 기준 20, 요구 전체 완료 근거 0**이다.
52항목은 전부 아래에 남기며 운영 기준을 제품 완료로 세지 않는다. 부분 구현은 기능이
존재하지만 해당 행 전체 업무가 끝나지 않았다는 뜻이다. 구체적인 진척은 위 인도와
기존 SPEC의 확인된 결과로 함께 보고한다.

<details>
<summary>52항목별 남은 작업과 근거</summary>



`남은 결과 / 근거`는 각 행을 지금 분류한 이유와 끝내야 할 구체 결과를 함께 적는다. 기능 행에는 기능 결과를 계속 표시하며 과거 단계로 돌리지 않았다.

| ID | 상태 | 남은 결과 / 근거 |
|---|---|---|
| R01 | 부분 구현 | CAD/FE, implicit·explicit, failure, constitutive/PDE·연성, numerical과 physical loop를 각 독립 지원 범위로 연결하고 미지원 조합은 분명히 남긴다; [PRODUCT_PLAN §1–2](docs/PRODUCT_PLAN.md), [FUNCTION_SPEC FN-06–24](docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md). |
| R02 | 부분 구현 | 같은 문서·명령·근거를 OpenScience 없이 GUI/CLI/Python에서 쓰고 필요한 AI 왕복을 선택 연결로 확인한다; [CODEX_WORKFLOW](docs/CODEX_WORKFLOW.md), [SPEC-EXPERT-002](.moai/specs/SPEC-EXPERT-002/spec.md). |
| R03 | 부분 구현 | 실제 대화와 deterministic 후보/solver 결과가 별개 owner·실행으로 보이는 전체 Expert→Plan→결과 장면을 확인한다; [FUNCTION_SPEC FN-20–30](docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md), [SPEC-EXPERT-002](.moai/specs/SPEC-EXPERT-002/spec.md). |
| R04 | 운영·조사·역사 기준 | pinned fixture 자산을 재사용할 adapter 경계와 나머지 일반 CAD 기능을 구별해 유지한다; pinned source SHA와 사용 위치는 [CURRENT_STATE](CURRENT_STATE.md), `plugins/fixture_design/upstream`이다. |
| R05 | 부분 구현 | Core/domain/plugin 경계가 코드와 사용자 문서에서 일관되고 신규 도메인 입력이 기존 owner를 재사용함을 확인한다; [ARCHITECTURE](ARCHITECTURE.md), [FUNCTION_SPEC §2–3](docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md). |
| R06 | 부분 구현 | 길이 외 CAD/FE 변수, typed region/load/material/contact parameter와 native binding·source가 보존되는 Registry 흐름을 완성한다; [SPEC-CAD-NUMERICAL-001](.moai/specs/SPEC-CAD-NUMERICAL-001/spec.md), [CURRENT_STATE](CURRENT_STATE.md). |
| R07 | 부분 구현 | 다양한 사용자 모델의 발견→명시 선택/등록→의미 변경·새로고침·저장 흐름을 확인한다; [FUNCTION_SPEC FN-10](docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md), [implementation_map.csv](docs/design/20261012-desktop-planning/pro-ux/implementation_map.csv). |
| R08 | 부분 구현 | invalid draft는 저장 가능하고 해당 export/evaluation만 오류 위치와 함께 차단되는 경로를 각 owner에서 끝낸다; [PROJECT_SCOPE 상세 acceptance](PROJECT_SCOPE.md), [FUNCTION_SPEC §4](docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md). |
| R09 | 부분 구현 | validator·threshold·revision·evidence가 검사별 상태로 남고 UNKNOWN/NOT_RELEASED가 실제 제품 결과까지 유지됨을 확인한다; [PROJECT_SCOPE 상세 acceptance](PROJECT_SCOPE.md), [REQUIREMENTS_VALIDITY_REVIEW Appendix A](docs/REQUIREMENTS_VALIDITY_REVIEW.md). |
| R10 | 부분 구현 | 원 field/곡선/메시/시험/교정/사진·보고를 해당 판단·revision에 따라 다시 여는 사용자 흐름을 마친다; [FUNCTION_SPEC FN-03–05, FN-27–32](docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md). |
| R11 | 부분 구현 | CAD 없는 Data/PDE/외부 결과도 가짜 CAD 선행 없이 source→result→evidence→decision으로 재개됨을 확인한다; [FUNCTION_SPEC FN-01, FN-18–19, FN-27–32](docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md). |
| R12 | 부분 구현 | 지정 원본·native 입력·실패 응답·중간 결과가 정확한 저장/보존 범위와 함께 재열기됨을 확인한다; [PROJECT_SCOPE 상세 acceptance](PROJECT_SCOPE.md), 각 기능 acceptance. |
| R13 | 부분 구현 | 실제 엔지니어 GUI와 headless CLI/Python/선택 MCP가 같은 owner와 최신 문서를 다루고 교차 변경·복구되는지 확인한다; [FUNCTION_SPEC FN-01, FN-34](docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md). |
| R14 | 부분 구현 | 역할별 Code_Aster/SALOME-MECA·CalculiX/PrePoMax 지원표와 독립 기준을 실제 선택 경로로 제한해 완성한다; [PROJECT_SCOPE R14](PROJECT_SCOPE.md), [CURRENT_STATE 접촉 기록](CURRENT_STATE.md), `docs/research/OPEN_SOURCE_CONTACT_INTEGRATION.md`. |
| R15 | 미착수·미확인 | OpenRadioss impact/drop 사용자 입력·전처리·실행·에너지/접촉 응답·실패 검증을 제품 경로로 수용하지 않았다; [FUNCTION_SPEC FN-16](docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md), [PROJECT_SCOPE R15](PROJECT_SCOPE.md). |
| R16 | 부분 구현 | 사용자 방정식·비선형/연성·AD/PETSc·mesh/HPC 필요별 PDE 지원 matrix와 reference 결과를 확정한다; [FUNCTION_SPEC FN-18–19](docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md), [PROJECT_SCOPE R16](PROJECT_SCOPE.md). |
| R17 | 부분 구현 | law별 상태·tangent·유한변형·코드생성·identifier 및 실제 solver interface 조합을 검증한다; [FUNCTION_SPEC FN-06–09](docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md), [PROJECT_SCOPE R17](PROJECT_SCOPE.md). |
| R18 | 부분 구현 | DOE/optimization/UQ/sensitivity/surrogate/MOO별 지원 method와 실패·resume·후보 adoption을 사용자 UI에서 구별한다; [FUNCTION_SPEC FN-20–24](docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md). |
| R19 | 부분 구현 | 공통 study/experiment 상위 envelope와 typed adapter extension이 실제 domain owner·저장 revision을 통해 호환되는지 확인한다; [PROJECT_SCOPE 상세 common schemas](PROJECT_SCOPE.md), [FUNCTION_SPEC §2](docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md). |
| R20 | 부분 구현 | 실제 결과에 units/validity/reason/raw reference와 solver quality가 빠짐없이 표시되고 invalid/missing값을 usable number로 만들지 않음을 확인한다; [PROJECT_SCOPE detailed acceptance](PROJECT_SCOPE.md), [FUNCTION_SPEC §4](docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md). |
| R21 | 부분 구현 | 전체 광고 기능을 GUI·CLI·Python·선택 MCP에서 동일 Core operation으로 제공하거나 unavailable capability로 명확히 보고한다; [FUNCTION_SPEC FN-34](docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md), [PROJECT_SCOPE R21](PROJECT_SCOPE.md). |
| R22 | 운영·조사·역사 기준 | 큰 신규 기반을 추가하기 전 기존 reader/engine/JobManager/native owner의 재사용·확장·폐기 근거를 기록한다; [CODEX_WORKFLOW](docs/CODEX_WORKFLOW.md), [FUNCTION_SPEC §3](docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md). |
| R23 | 운영·조사·역사 기준 | 옛 Phase 0 선형 순서는 종료 기준에서 제외하고 실제 연결에 필요한 최소 계약만 유지한다; 적용된 순서 규칙은 [REQUIREMENTS_VALIDITY_REVIEW Appendix A](docs/REQUIREMENTS_VALIDITY_REVIEW.md), 새 작업 증거는 [CURRENT_STATE](CURRENT_STATE.md). |
| R24 | 운영·조사·역사 기준 | 중대한 계약 변경 때에만 이유·대안·요구 영향·필요 시험을 ADR에 남긴다; 문서 소유/범위는 [CODEX_WORKFLOW](docs/CODEX_WORKFLOW.md), 기존 판정은 [ADR_APPLICABILITY](docs/ADR_APPLICABILITY.md). |
| R25 | 부분 구현 | 새 독립 Expert 화면에서 실제 대화→편집 가능한 Plan→native 계산→결과 근거→후속 논의를 잇는다; [SPEC-EXPERT-001](.moai/specs/SPEC-EXPERT-001/spec.md), [SPEC-EXPERT-002](.moai/specs/SPEC-EXPERT-002/spec.md). |
| R26 | 부분 구현 | 사용자 CAD의 editable 조립·접촉·실제 mesh/implicit response를 기준 비교·설계 개정까지 연결한다; [SPEC-CONTACT-001](.moai/specs/SPEC-CONTACT-001/spec.md), [CURRENT_STATE](CURRENT_STATE.md). |
| R27 | 부분 구현 | frozen input·실패 응답·optimizer state를 보존하면서 계산 후보를 정확히 비교/재개/명시 채택한다; [SPEC-NUMERICAL-001](.moai/specs/SPEC-NUMERICAL-001/spec.md), [SPEC-CAD-NUMERICAL-001](.moai/specs/SPEC-CAD-NUMERICAL-001/spec.md). |
| R28 | 부분 구현 | CAD 없이 식/약형식/ODE/PDE를 직접 바꾸고 지원 adapter reference와 비교한다; [FUNCTION_SPEC FN-18](docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md), [PROJECT_SCOPE R28](PROJECT_SCOPE.md). |
| R29 | 부분 구현 | 지원표에 올린 선형·기하/재료 비선형·contact·hyperelastic·viscoelastic의 각 독립 기준 비교를 둔다; [PROJECT_SCOPE R29](PROJECT_SCOPE.md), [FUNCTION_SPEC FN-14–15](docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md). |
| R30 | 미착수·미확인 | 실제 explicit impact/drop의 초기속도·중력·접촉·힘/가속도·에너지·시간 증분·failure를 새 결과에서 검증한다; [FUNCTION_SPEC FN-16](docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md), [PROJECT_SCOPE R30](PROJECT_SCOPE.md). |
| R31 | 부분 구현 | inverse/UQ/sensitivity/surrogate/MOO, multiphysics와 remote/HPC/physical 연계의 지원 범위를 각 실제 선행과 함께 끝낸다; [FUNCTION_SPEC FN-19–26, FN-35](docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md). |
| R32 | 미착수·미확인 | 시편·장착·장비·교정·측정·내구 raw evidence로 model/Plan을 갱신하고 다음 실험을 저장한다; [FUNCTION_SPEC FN-05, FN-35](docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md), [PROJECT_SCOPE R32](PROJECT_SCOPE.md). |
| R33 | 부분 구현 | Design/Simulation/Explore/Results/Research 작업을 browser 시안에 한정하지 않고 각 선택 native/desktop 도구에서 완료한다; [PRODUCT_PLAN §1–3](docs/PRODUCT_PLAN.md), [FUNCTION_SPEC](docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md). |
| R34 | 부분 구현 | 지원된 CAD invalid gating·linear/nonlinear/contact/explicit/PDE/DOE/optimization의 기준·저장/GUI regression과 physical approval 경계를 증명한다; [PROJECT_SCOPE R34](PROJECT_SCOPE.md), [FUNCTION_SPEC VERIFICATION PLAN references](docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md). |
| R35 | 부분 구현 | 채택·배포할 dependency별 license/link/redistribution, supported OS/runtime 및 자료·telemetry 경계를 사용자 설치 경로와 함께 확인한다; [PROJECT_SCOPE R35](PROJECT_SCOPE.md), [FUNCTION_SPEC FN-33](docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md). |
| R36 | 운영·조사·역사 기준 | private-repo 시도/기존 저장소 관계는 역사 참조만 유지하고 요구행 충족을 위해 저장소를 다시 옮기지 않는다; 출처/현재 upstream은 [PROJECT_SCOPE R36](PROJECT_SCOPE.md), [CURRENT_STATE](CURRENT_STATE.md). |
| R37 | 운영·조사·역사 기준 | 분리 가능한 구현·검토만 병행하고 shared interface owner를 두며 agent 수를 제품 진척으로 세지 않는다; [CODEX_WORKFLOW](docs/CODEX_WORKFLOW.md), 현재 배정은 [CURRENT_STATE](CURRENT_STATE.md). |
| R38 | 운영·조사·역사 기준 | Root가 공통 계약/registry/provenance 통합과 개발 판정을 맡고 사용자·공학 수용을 대신한다고 주장하지 않는다; [AGENTS](AGENTS.md), [CODEX_WORKFLOW](docs/CODEX_WORKFLOW.md). |
| R39 | 운영·조사·역사 기준 | 실제 backend 선택의 의사결정에 필요한 공식 자료·지원 한계를 조사하고 조사 자체를 매 작업 선행으로 만들지 않는다; 활성 자료는 [OPEN_SOURCE_CONTACT_INTEGRATION](docs/research/OPEN_SOURCE_CONTACT_INTEGRATION.md), 기준은 [PROJECT_SCOPE R39](PROJECT_SCOPE.md). |
| R40 | 운영·조사·역사 기준 | optimizer 후보 순위표 대신 R18의 실제 문제 유형/역할과 기존 비교 근거를 합쳐 사용한다; [PROJECT_SCOPE R18/R40](PROJECT_SCOPE.md), [REQUIREMENTS_VALIDITY_REVIEW Appendix A](docs/REQUIREMENTS_VALIDITY_REVIEW.md). |
| R41 | 운영·조사·역사 기준 | fixture upstream의 실제 adapter·테스트·CI 재사용 접점을 변경 영향 때만 재확인한다; pinned SHA/접점은 [CURRENT_STATE](CURRENT_STATE.md), [PROJECT_SCOPE R41](PROJECT_SCOPE.md). |
| R42 | 운영·조사·역사 기준 | 연구/Pro 구현/Astra 독립 검토/Codex 통합 역할을 실제 작업과 근거에 표시한다; [CODEX_WORKFLOW](docs/CODEX_WORKFLOW.md). |
| R43 | 운영·조사·역사 기준 | 공통 adapter/API/parser/optimizer/validation 등 영향 큰 계약만 독립 검토를 거친다; [AGENTS](AGENTS.md), [CODEX_WORKFLOW](docs/CODEX_WORKFLOW.md). |
| R44 | 운영·조사·역사 기준 | 공유 schema/Core/registry/artifact migration의 단일 소유와 동시수정 조정을 적용한다; [AGENTS](AGENTS.md), [CODEX_WORKFLOW](docs/CODEX_WORKFLOW.md). |
| R45 | 운영·조사·역사 기준 | 각 통합에서 실제 GUI/headless, feasibility, evidence, security/license와 현재 사용자 결정을 범위대로 점검한다; [CODEX_WORKFLOW](docs/CODEX_WORKFLOW.md), [CURRENT_STATE](CURRENT_STATE.md). |
| R46 | 운영·조사·역사 기준 | 논점 난이도에 맞는 조사·검토와 정확한 실행 근거를 적용하되 모델명/agent count를 완료 지표로 쓰지 않는다; [CODEX_WORKFLOW](docs/CODEX_WORKFLOW.md). |
| R47 | 운영·조사·역사 기준 | 중요한 독립 질문·근거·교정·채택/기각 사유를 정확한 코드/run/문서에 기록한다; [CURRENT_STATE](CURRENT_STATE.md), dated acceptance records. |
| R48 | 운영·조사·역사 기준 | 기능 추가 전에 필요한 경로에서 실제 실행/실패 복구를 확인하고 같은 suite/native campaign을 이유 없이 반복하지 않는다; [AGENTS](AGENTS.md), [CODEX_WORKFLOW](docs/CODEX_WORKFLOW.md). |
| R49 | 운영·조사·역사 기준 | 새 세션은 CURRENT_STATE와 source/run 존재를 확인하고 초기 구축/옛 R 단계부터 재시작하지 않는다; [CURRENT_STATE](CURRENT_STATE.md), [CODEX_WORKFLOW](docs/CODEX_WORKFLOW.md). |
| R50 | 부분 구현 | 기존 CAD–Runner–Post 계산 근거를 새 CAD 변수/FE 후보·결과 기반 설계 채택으로 이어 사용자 모델에서 다시 연다; [SPEC-CAD-NUMERICAL-001](.moai/specs/SPEC-CAD-NUMERICAL-001/spec.md), [SPEC-CONTACT-001](.moai/specs/SPEC-CONTACT-001/spec.md). |
| R51 | 운영·조사·역사 기준 | 중요 architecture/interface 변경의 이유·대안·요구 영향과 필요한 검증만 기록한다; [ADR_APPLICABILITY](docs/ADR_APPLICABILITY.md), [CODEX_WORKFLOW](docs/CODEX_WORKFLOW.md). |
| R52 | 운영·조사·역사 기준 | 진척 지표를 요구행 개수 대신 아래 8개 고정 사용자 업무 묶음의 완료 조건으로 관리한다; [REQUIREMENTS_VALIDITY_REVIEW §7](docs/REQUIREMENTS_VALIDITY_REVIEW.md), [PRODUCT_PLAN](docs/PRODUCT_PLAN.md). |


</details>

## 기존 결정과 구현 근거

**기획·Qt 시제품을 바탕으로 본제품의 기능 단위 구현에 착수한다.** 사용자의
“왜 말만 하고 아무것도 안 하고 있는 것처럼 보이지?”와 시작 주체에 대한 후속 지시를
작업 진행 권한으로 받아 다음 별도 문구를 기다리지 않는다. 제가 과제를 배정·시작·검증·
통합하며 MoAI는 제가 사용하는 SPEC·작업 관리 도구다. 기존 전체 배정은 운영 지침의
충돌 정리, 전체 개발 명세·작업 목록, 편집 가능한 작업/화면/상태 설계와 상호작용 시안,
Qt 조작 확인, 실제 Pro 작성과 Astra 독립 검토다. Windows 로컬 Qt/PySide6·FreeCAD·
ParaView와 추가 지출0원을 유지한다. 과거 문서의 기획 완료·다음 구현은 이번 수용 근거가 아니다.

2026-10-13 사용자가 전체 명세에 따른 독립 도구·전체 연계 구현과 통합을 지속 목표로
등록했다. 각 도구는 데스크톱앱이며 이를 묶는 선택적 연결 화면은 웹 또는 데스크톱으로
제공할 수 있다. 기능 개발이 우선이고 개별 도구는 실행 가능 여부와 필요한 단위 검사만
확인한다. 넓은 통합·수치 검증은 관련 구현 이후다. 미완료 기능이 있으면 같은 작업을
계속하며, 작은 검토·교정마다 재승인이나 전체 solver 검증을 기다리지 않는다.

최근 사용자 지시는 CAD/전처리→solver/Runner→native Post→최적화와 Co-STORM 연구의
독립 작업·도구 연결을 중심으로 완성하는 것이다. Material 예시를 전체 우선순위로 확대하지
않으며 그 교정이 다른 도구를 기다리게 하지 않는다. Data/Material/PDE/Numerical/Runner/
Expert/Study·선택 Workbench와 넓은 물리·수치 범위는 그대로 유지한다.

이전 설명문·보조 기능이 많은 Qt 폼은 **사용성 미수용 초안**으로 보존했다. 새 Qt 시안은
모델·표·곡선과 선택한 작업을 중심으로 교정해 **사용자 검토본**으로 통합했다.
[화면과 시제품 검토](docs/design/20261012-desktop-planning/REVIEW_GUIDE.md)에서 시작한다.
설계 작성·통합, 사용자 화면 수용과 제품 구현 완료는 구별한다. 사용자 화면 피드백은
구현 중에도 반영하며 시제품을 본제품으로 복사하거나 합성 계산을 실제 계산으로 바꾸지 않는다.
최신 사용자 설명: **“그냥 물어본건데 혼자서 잘못한걸 찾네. 제발 전체 과제 맥락에서
유기적으로 생각해. 독립 프로그램으로도 사용가능하지만 전체 시스템에서 연계도 되어야해.”**
Codex는 앞선 중립 질문을 결함·재설계 요구로 확대해석한 것을 바로잡았다. 현재 목표는
각 독립 도구의 직접 사용과 모델→해석/Runner→Post→응답→최적화→설계 적용,
Expert→계획→결과 근거→후속 논의/Study의 전체 연결을 함께 설명·설계하는 것이다.
Workbench는 선택적 연결 보기이며 강제 진입점이 아니다. 기존 시제품·조작 검사·기능
명세를 재사용한다. 독립 사용과 전체 연결을 함께 구현한다.
같은 실제 Pro의 `UX-REVIEW-CLARITY-01`에 최신 사용자 원문과 해석 교정을 전달했다.
Pro `5b9ae1c`의 DESIGN/README 교정을 확인해 통합했다. 내용은 독립+전체 연계의 맥락
설명이며 추가 결함 찾기나 별도 재설계 과제가 아니다. Qt 소스·시안·기능/작업표·조작
검사 상태는 유지했다. MoAI SPEC 조회와 실제 Pro 연결을 다시 확인했다.

첫 제품 작업 `PRO-IMPL-DESKTOP-20261013-01`의 Windows 기본 데스크톱 진입과 기존
문서·서비스를 사용하는 독립 도구 실행을 구현·검증했다. 기본 browser Workbench
진입을 기존 native Qt Runner로 바꾸고 각 Research 도구에 직접 들어간다. CLI/direct
native Pre/Post와 공유 저장소를 재사용하며 새 문서·서비스를 강제로 만들지 않는다.
Luna는 시작·서비스 수명, Sol은 Numerical/Expert의 실제 명령 연결을 읽기 전용 조사했다.
실제 Pro가 제품 코드·테스트를 주작성하고 Astra가 독립 설계·코드 검토를 맡는다.
다음 기능 단위는 기존 Numerical Plan의 변수·응답·방법 중심 편집과 Expert/Study의
정확한 결과 왕복이다. 전체 제품을 첫 진입 기능으로 완료 처리하지 않는다.
사용자는 긴 제목·파일명에
`• r2` 등 내부 접미사를 이어 붙이는 표시를 싫어한다. 주 화면은 짧은 작업명·값·단위·선택·
상태·다음 조작을 보여주고, 정확한 원본/개정/실패는 이력·근거·진단에서 조회한다.
이미 지정한 FreeCAD/ParaView/HyperStudy/Co-STORM/Origin/MCalibration/COMSOL 원형은
[PRODUCT_PLAN §3](docs/PRODUCT_PLAN.md#3-화면마다-주-기준을-고정한다)을 따른다.
참고 이미지를 사용자에게 요청하지 않는다. 세부 화면 시안은 검토용 제안이며 사용자 결정과 구별한다.

첫 구현 전 제품 source는 `9a6e3083037630b45694b812b135dc1cd63cf95a`, upstream은 아래 핀이다.
첫 제품 코드·테스트는 실제 Pro `9d6d780`을 통합해 Windows에서 확인했다.
solver/provider 실행은 시작하지 않았다. 사용자
`.codex-remote-attachments/`와 기존 설정·AGENTS를 보존한다.

### 실제 Pro 원고와 검토

실제 Pro/GPT-6·power5/5를 UI에서 확인하고 원문 요구·기준 source를 전달했다.
[원 D1 대화](https://chatgpt.com/c/6acca3ab-15b0-83ee-8ca3-25ff00e335c5)의
[기능·구현 명세](docs/design/20261012-desktop-planning/pro-authored/README.md)를 회수했다.
이 원고는 전체 제품 설계의 자료이며 새 GUI 수용을 대신하지 않는다.
같은 [실제 Pro 대화](https://chatgpt.com/c/6accef3a-e650-83ee-89e2-3f48a60dd17a)에 첫 제품
구현 요청 `PRO-IMPL-DESKTOP-20261013-01`을 전달하고 수신을 확인했다. 작성 브랜치는
`codex/desktop-tools-20261013`, 기준은 `c2e506b`다. Pro는 시작 스크립트·최소 desktop
진입 연결·관련 테스트/사용 안내를 소유하고 Codex는 현황/SPEC/통합을 소유한다.
앞선 기획 요청06의 소유권은 `pro-ux/`, 작성 브랜치는 `design/product-ux-20261012`였다.

최종 Qt view와 상태/도면 연결은 Pro `dd43015`다. Report/Acquisition 추가 `600f9f8`,
문서/작업 대응 `a2e20b8`, scatter 교정 `0b9da54`, 정확 선택/출력 교정 `9e313e5`를 포함한다.
최종 검사 helper 두 줄과 Pro의 Windows 인계 기록은 `20291b3`으로 회수했다.
CAD/FE·Simulation·Runner·Post·Numerical·Expert·Study와
Data/Material/PDE/Evaluation/선택 Workbench의 Qt 창을 실제로 렌더링했다.
[GUI 실제 검토](docs/design/20261012-desktop-planning/GUI_REVIEW.md)에 source별
Pro 작성, Astra/xhigh 독립 검토, Sol/high의 실제 입력 검사와 Codex 통합 확인을 구별한다.
지수 입력·Undo/Redo·잘못된 입력의 보존/실행 차단·수정, 새 연구 계획의 변수/응답 정의,
Post의 시간/필드 연동과 CAD→Simulation→Runner의 합성 결과→Post→MOO 명시 적용/
개별 저장→저장 실패 재시도→새 창 재열기를 확인했다. 실제 계산이나 engineering 승인이 아니다.

Astra의 `48cbac3` 재검토는 스케치 선 삭제, saved 자세/instance·비교 형상,
selected step, inverse train/holdout 및 방법별 결과→후속 논의의 잔여를 찾았다.
같은 Pro에 UX-FIX-04로 전달했고 최신 core의 집중 Qt 검사에서 sketch 보존·saved 형상/
selected step·Post ordinary file 재열기·방법별 결과→Expert→Study 경로를 확인했다.
상태 SVG/JSON과 작업 흐름 drawio, 기존74task의 새 화면 연결을 회수했다.
Astra의 최종 changed-path 검토는 step 이름 변경 시 입력 유실, 같은 결과의 발언별
locator 혼합, Numerical 기능/화면 대응 오류를 찾았다. UX-FIX-06/UX-MAP-01로 같은 Pro에
교정을 맡겼다. Luna의 독립 대응 검토는 FN-01/32/34/35의 전용 경로·기존 상세 계약 참조가
불명확한 것을 찾아 UX-MAP-02로 전달했다. 원74task/기존열·52요구 상태는 유지됐다.
Windows 글꼴과 Post 비교값 잘림은 UX-FIX-05/UX-VISUAL-01로 교정됐고 정상 글자와
0.31/0.29mm 첫 표시를 실제 렌더에서 확인했다. 무료 기존 폰트를 읽으며 배포하지 않는다.
`049bbbc`의 입력/발언 근거 두 문제는 root 실제 Qt 검사와 Astra 독립 재현에서 해소됐다.
`60a4fab`의 task/state 대응 교정은 Luna의 제한된 재검토로 확인됐다.
Pro의 원격 Linux 실행 환경이 끊겼으나 GitHub 연결로 Report/Acquisition 소스를 계속
주작성·게시했다. root Windows에서 새 4상태의 실제 Qt 렌더를 확인했다. Sol/high는
PDF/Markdown·보고서 일반 저장/cold reopen, 채널 Cancel/단위변환/표곡선/부분입력 차단/
저장/cold reopen과 unavailable live guards를 실제로 확인했다. Astra는 구조·시각을 검토했다.
선택 .02s 보고서가 끝 .04s 값 .31을 쓰는 오류, 미리보기 페이지와 source 열기 불일치,
출력 근거 참조·F05 역사 적용범위·Use Study 교체·Acquisition 종료 표시를 같은 Pro에
UX-REPORT-FIX-01/02로 전달했다. `9e313e5` 교정은 독립 Sol/high의 정확 시각/출력/
Cancel/Undo/cold reopen과 Astra/xhigh의 페이지/출처/역사 적용범위/6행 표시 검사에서
닫혔다. `dd43015`의 supported gauge·Surface 복원/overflow 이동은 Sol 제한 소스 검토와
root Windows의 변경 경로 Qt 검사에서 확인했다. 숫자 delegate로 보였던 검사 실패는
offscreen 모달 종료 뒤 검사 창 활성화 누락이었다. 기존 delegate는 생성됐고 올바른
창 활성화 뒤 부분 입력·수정·저장/재열기가 작동했다. root는 ignored 검사 사본의
포커스만 보완했으며 제품 작성자로 대체하지 않았다.

최종 56상태 SVG와 화면 미리보기는 같은 Pro 소스를 root가 Windows Qt에서 재생성했다.
같은 원본의 네 작업 흐름 페이지를 draw.io Desktop에서 export했고 PDF의 정확 .02s/
.2294mm 표·곡선·글자·출처를 Poppler로 렌더해 확인했다. 실행 안내, 전체 명세/작업표,
MoAI 인계와 연결해 검토본으로 저장했다. 숫자는 합성 예시이며 실제 계산 통과가 아니다.
최종 전달의 Git 게시 결과와 사용자 수용을 구별한다.

Edge 연결 소실 후 공식 task 조회로 요청06과 원 UI의 같은 turn을 대조해 후속 연결을
복구했다. 작성 task는 `01a13087-154b-7343-ad70-1f882d9fc0af`/durable,
turn은 `01a13087-26c6-7536-b617-db0dbef22557`다.
공식 전송 뒤 수신 userMessage의 UX-FIX-04/05/06, UX-MAP-01/02,
UX-VISUAL-01/UX-COMPLETE-01 본문·끝 경계를 확인했다.
새 모델·유료 API 또는 다른 작성자로 대체하지 않는다. 최신 사용자 요구와 실제 원고의
전달 요약은 [PRO_UX_REQUEST](docs/design/20261012-desktop-planning/PRO_UX_REQUEST.md)다.
Space 제품 입구에도 GUI/우선순위 결정과 같은 Pro/Qt 링크를 반영·재조회했다.
기존 과거 원문·ZIP 참조를 보존하며 현행 상태의 원본은 이 파일이다.

### 도구와 실제 확인 범위

MoAI `3.2.0-dev.2aab5f7`의 공식 Codex 초기화를 분리해 확인한 뒤 필요한 설정만 병합했다.
실제 skill catalog의 MoAI5개, local stdio initialize/tools와 현재 host MCP4개를 확인했고
이번 재개에서도 `spec_progress`로 SPEC을 조회했다. [기획 SPEC](.moai/specs/SPEC-DESKTOP-001/spec.md)은
기능·화면·작업표·수용 조건에 연결하며 현재 큐를 중복하지 않는다. strict lint는 구조 검사이며
사용성 통과가 아니다. hook trust는 미확인이다. CLI0.146.1의 기존 global context_management
map 호환 오류는 read-only 검사에만 임시 override를 사용했고 사용자 설정을 덮어쓰지 않았다.
첫 제품 구현은 [SPEC-DESKTOP-002](.moai/specs/SPEC-DESKTOP-002/spec.md)에 연결했다.
Astra의 독립 검토에서 모드별 서비스 준비/UI 억제, PrepareOnly 실패의 비대화형 처리,
새 runtime의 ResearchUI 설치를 명시했다. CMD pause·축약 옵션·환경 경계와 실제
WinPS 5.1 readiness 인수 손상을 같은 Pro가 교정했다. 실제 기본 CMD의 native Runner
창, 저장된 Data ID의 native 창과 같은 서비스 PID 재사용을 확인했다. 관련 진입·
Windows 경로·native argv 검사가 통과했고 source guard가 기존 서비스를 유지하는
오류 경로도 확인했다. 정확한 소스·대역/실제 실행·잔여 한계는
[진입 기능의 검증 기록](.moai/specs/SPEC-DESKTOP-002/acceptance.md)에 있다.

기존 사용자 Python3.13에는 PySide6 6.9.1·Matplotlib3.10.1·Designer와 Qt SVG가 있다.
앞선 기존 Research runtime의 PySide6 미설치와 별도로 이번 진입 검증용 private
runtime에 프로젝트의 Qt 의존성을 설치했다. 새 D1 Qt 프로세스/접근성 구조는 확인했지만
창 활성화 실패와 검은 캡처 때문에 native 입력을 중단했다. Segoe UI offscreen 렌더링·
QTest의 범위만 기록한다. 이전 [Qt spike 검토](docs/design/20261012-desktop-planning/QT_REVIEW.md)의
CSV/저장 chooser·선택·채택·Undo/Redo·dock Float·새 프로세스 재열기 근거가 새 D1을 대신하지 않는다.
앞선 제한된 경로 검색 이후 `runs/prepost-session-20261008-01/tools`에서 기존 portable
FreeCAD1.1.4와 ParaView6.2.0을 찾았다. 새 설치 없이 ParaView의 실제 pvpython으로 공개
합성 3시각 자료의 한 점 시간 측정을 Apply·sample·저장했다. 실제 표의 Time은 0/.5/1s,
명시적으로 고른 `avg(U (2))`는 0/1/2mm다. 이 자료는 새 Post→Numerical 연결 확인용이며
solver 계산·native 마우스 조작·공학적 검증이 아니다. FreeCAD는 실행 파일 존재만 확인했다.
정확한 경로·재사용 자료는 [Post 연결 실행 준비](.moai/specs/SPEC-POST-NUMERICAL-001/acceptance.md#native-input-prepared-on-windows)에 있다.
이 실행 파일 둘을 기존에 없던 사용자 `LOCALAPPDATA/AutonomousCAELab/workbench-config.json`의
desktop 설정에 연결했다. 다음 서비스 시작부터 적용하며 열린 서비스/문서는 중단하지 않았다.
소유한 개발 runtime에는 기존 `install-windows.ps1 -ResearchUI -Documents`로 프로젝트에
고정된 pypdf6.10.0을 추가해 PDF reader import를 확인했다. BSD 라이선스 원문을 확인했으며
provider 설정·인증·추가 비용은 없다. 실제 Expert 파일 가져오기는 다음 구현에서 연결한다.

draw.io Desktop32.4.1의 기존 portable 무료 도구로 Codex의 소유권·상태 도면을 열기/export했다.
Pro 계약에서 작성한 [전체 연결 원본](docs/design/20261012-desktop-planning/research.drawio)은
CAD/FE 준비·실행/Post·최적화/채택·Co-STORM/Study 경로를 연결하며 CLI export/렌더링을 확인했다.
프로그램 화면 또는 solver 실행의 대체물이 아니다. Desktop 해당 버전 라이선스는 GPLv3로 교정했다.
Penpot은 계정이 없어 제외하라는 사용자 결정으로 닫고 무시하며 계정·편집·export를 완료 gate로 두지 않는다.
[무료 도구 기록](docs/design/20261012-desktop-planning/TOOLS_AND_LICENSES.md)을 따른다.

주 Codex는 사용자 변경 이후 실제 실행 기록에서 Sol/xhigh를 확인했다. 변경 전 Sol/high
기록을 소급 변경하지 않는다. 핵심 독립 검토 Astra/xhigh, bounded 코드 Sol/high,
코드 조사 Luna/high를 사용했다. 실제 Pro UI 설정과 Codex의 추론 수준은 별개다.
브라우저의 기존 대화 회수 장애를 공식 파일/저장소 작업 전체의 금지로 확대하지 않는다.
수동 다운로드 요청은 공식 회수 경로가 동작한 뒤 철회했고 추가 사용자 조작을 기다리지 않는다.

### 이어서 할 작업

첫 진입 기능은 원격 main에 반영했다. 실제 Pro `39c5fb0`의 Numerical 변수·응답·방법
편집과 원래 Expert/Study 결과 전달, `43ef92f`·`433d681`의 교정을 로컬 `d010303`까지
통합했다. 컴파일과 작은 실제 DOE·최적화, 정밀/부분 입력 저장·재열기를 확인했다.
첫 fixture의 5초 제한 초과, Expert 소켓 응답 실패와 Windows venv PID 가정 오류는
보존했다. Pro가 같은 프로세스의 결과 전달을 GUI 스레드에서 처리하도록 고쳤고
Expert/Study/독립 대상 선택/이전 결과 선택 4개 단위 검사가 통과했다. 별도 프로세스의
실제 Qt 창에 Attach하고 기존 편집을 보존하는 검사도 통과했다. 실제 desktop 진입에서
1440×900 generic worksheet Qt 렌더를 확인했다. 검사별 소스·한계는
[Numerical 구현 기록](.moai/specs/SPEC-NUMERICAL-001/acceptance.md)에 둔다.
이 단위의 기본 실행을 확인했으며 전체 제품 수용·넓은 통합 검증은 아직 남아 있다.
Astra/xhigh의 좁은 소스 검토에는 새 blocking/data-loss 지적이 없었다. 실행 결과와는
별개이며 표시 개선 두 건은 후속 UX로 남긴다. Codex가 Windows 실행·통합을 맡는다. 열린
원 창의 미적용 편집을 보존하고 pending 결과를 사용자 확인 후 추가해야 한다.
같은 문서를 새로 열거나 새 X/S를 만들며 왕복 완료로 표시하지 않는다.
원 구현 요청은 `PRO-IMPL-NUMERICAL-20261013-01`, 작성 브랜치는
`codex/numerical-workflow-20261013`, 기준 main은 `edcc1fb`다.
범위와 완료 조건은 [SPEC-NUMERICAL-001](.moai/specs/SPEC-NUMERICAL-001/spec.md)에 연결한다.
첫 진입 기능과 배정 기록은 원격 main `c6e7f2e` 게시 후 같은 SHA를 확인했다.
Luna/high가 기존 native CAD/FE→Runner→Post 연결과 Post→Numerical의 빠진 연결을
읽기 전용으로 조사했다. 같은 Pro에 `PRO-IMPL-POST-NUMERICAL-20261013-01`을 전달했다.
Numerical 교정 커밋 후 `codex/post-numerical-20261013`을 만들고 저장된 Post 측정의
실제 표·곡선을 Numerical 관측/응답으로 가져와 편집·저장·재열기하는 제품 기능을 작성한다.
원래 native 편집기·JobManager·Data/evaluation/Numerical owner를 재사용한다. 기존 Plan의
미적용 편집을 보존하며 새 후보 계산과 측정값 가져오기를 구별한다. shared Core 변경은
Codex가 통합하며 같은 소스의 작성자는 Pro 한 명이다. 범위는
[SPEC-POST-NUMERICAL-001](.moai/specs/SPEC-POST-NUMERICAL-001/spec.md)에 연결했다.
Pro `f313bb1`의 backend와 `1456e29`의 Qt 선택·관측 화면, 문자열 손상을 고친 `4563ec8`을
로컬 `7325175`까지 통합했다. 처음 UI 소스는 문법 오류로 collection 실패했고 같은 Pro가
즉시 교정했다. 변경 경로 검사 6개가 통과했고 실제 native 자료를 넣은 1100×780 Qt
대화상자의 표·곡선·선택 연동을 렌더로 확인했다. 앞선 ParaView6.2 owner의 실제 측정 추출과
UI의 native transport 대역은 구별한다. Astra가 지적한 물리 선언·무효 행 품질 두 문제도
교정 소스에서 해소됐다. 확인 범위와 원 실패는 SPEC의 acceptance에 남긴다.
같은 대화상자에서 기존 Plan을 직접 선택하고 미적용 편집에 관측값만 검토 후 추가하는
경로도 Pro `3d730ff/f015825/f966b52`를 로컬 `0759f86`까지 통합했다. 처음 테스트 대역이
Numerical 문서 읽기를 잘못 거절했으나 Pro가 실제 Workbench 위임으로 교정했다.
Astra가 찾은 검토창 중 자동 갱신 경합과 프로세스 생성 전 실패 뒤 재시도 차단도
교정했다. Root의 최신 변경 경로 4개 검사는 6.24초에 통과했다. 실제 Qt 검토창에서
자동 갱신 중 Cancel/Append, 기존 편집·명시 저장·중복 전달, 실행 실패 후 재시도를
확인했다. native transport는 명시적 대역이며 실제 OS 입력/전체 native 왕복은 아직이다.
짧은 행 표시의 제품 Qt 렌더도 확인했다. SPEC은 implemented이며 전체 제품/공학 수용은
아니다. 기존 실패와 정확한 확인 범위는 acceptance에 보존했다.
MoAI MCP의 실제 SPEC 조회와 CLI의 상태 갱신·해당 SPEC lint를 사용했다. lint의 구조
오류는 수정했으며 표에 연결한 수용 조건을 인식하지 못한 coverage 등 경고는 남아 있다.
문서 lint 결과를 실제 제품 기능이나 테스트 통과로 바꾸지 않는다.
추가 MoAI `ast-grep` 호출은 실행기와 검사 규칙이 없어 실제 scan NOT_RUN이었다.
도구 목록의 존재를 검사 실행으로 기록하지 않으며 개발을 멈추는 조건으로 삼지 않는다.
이어지는 Expert 작업은 [SPEC-EXPERT-001](.moai/specs/SPEC-EXPERT-001/spec.md)의 로컬
자료 가져오기·선택·본문/인용 열기다. Luna/high가 기존 역할·개입·저장·Plan 연결을 확인했고,
Codex가 첫 파일 가져오기와 선택한 문서/개정의 검색·위임 경계까지 범위를 보완했다.
`PRO-IMPL-EXPERT-20261013-01`을 같은 실제 Pro 대화에 전달했고 실제 userMessage
`01a1339c-bc53-773b-b783-4d0c7729cf5e`에서 수신을 확인했다. Post 교정 커밋 후
별도 재승인 없이 Expert를 작성하도록 맡겼다. SPEC은 in-progress이며 작성 브랜치는
`codex/expert-sources-20261013`이다. 기존 KnowledgeStore와 문서 owner를 재사용하고 무료 inference가
실제로 가능한지는 별도 확인한다. 자료 선택·저장은 provider 연결을 기다리지 않는다.
Pro의 첫 자료 연결 커밋 `7090d1c`를 `c409665`로 통합했다. 선택한 문서의 정확한
개정 읽기·검색, 논의 이력·하위 전문가·OpenScience의 같은 선택 범위와 파일 업로드
클라이언트를 포함한다. Astra/xhigh는 변경 8개 파일을 독립 소스 검토해 실질적 결함을
찾지 못했다. Codex의 `tests/test_expert_sources.py`는 Windows에서 4 PASS/5.42s였다.
모델/호스트는 명시적 검사 대역이며 실제 inference는 실행하지 않았다.
이어 Pro `5037e46`의 파일 선택·본문 미리보기·첨부 화면을 `1170af4`로 통합했다.
실제 loopback HTTP/자료 저장소를 쓰는 Qt 검사4개가 6.57s에 통과했고 새 legacy 이력
검사도 1 PASS/1.75s였다. 종료 후 남은 worker의 Signal source deleted 예외는 같은 Pro에
교정 요청했다. 공개 Markdown/text PDF/CSV3개를 실제 import한 Qt 렌더에서도 원문과
질문·자료3개가 보였다. 다만 재열기 직후 원문 읽기와 제목 조회가 겹쳐 Source1/2/3으로
남는 문제, Astra가 찾은 주기 갱신 때 선택 해제와 다른 논의에 이전 원문이 남는 문제도
같은 Pro에 전달했다. Pro `5d6b970`을 `e1903e6`로 통합했고 자동 갱신·원문/과거 인용·
문서 전환·늦은 worker 종료를 포함한 수정 Qt 검사4개가 6.50s에 통과했다. 종료 예외도
재발하지 않았다. 최신 `expert-preview-886155b1`의 실제 Qt 렌더에서 자료3개의 파일명과
선택 원문을 확인했다. 교정 종료는 Codex의 소스/실행 확인이며 Astra 재통과 주장이 아니다.
MoAI CLI로 로컬 자료 기능 SPEC은 implemented, 후속 접촉 SPEC은 in-progress로 갱신했다.
`runs/product-development/20261013/expert-preview-63bea349`에 실제 화면/receipt가 있다.
모델 미설정 상태의 로컬 자료 작업이며 실제 inference/OS 입력을 확인한 것은 아니다.
첫 렌더 helper는 등록 역할이 반드시 있다고 잘못 가정해 대기했고, 그 가정만 제거한 뒤
정상 렌더했다. 제품의 역할 목록을 가짜로 채우지 않았다. Expert 전체 완료는 아직이다.
MoAI sync의 SPEC/코드 차이 대조와 관련 문서 갱신 절차를 적용했다. 전체 자동 sync나
추가 모델 호출을 실행한 것으로 표시하지 않으며, 기존 사용자 지시대로 변경 경로만 확인한다.
후속 CAD/FE 접촉 조사에서는 native 면 선택·참조 복구는 있으나 사용자 모델의 접촉쌍과
일반 solver 전달이 없는 점을 확인했다. 고정된 Code_Aster 기준 예제를 사용자 모델 경로로
대체하지 않는다. FN-14의 접촉 편집부터 solver/Post 결과까지 전체 요구는 계속 미완료다.
이를 [SPEC-CONTACT-001](.moai/specs/SPEC-CONTACT-001/spec.md)에 후속 구현으로 구체화했다.
기존 FreeCAD contact 객체·입력 작성기를 재사용하고 여러 면·마찰·간극·참조 수리와
Runner/Post 결과까지 연결한다. 별도 설정의 FreeCADCmd로 공개 합성 두 박스의 접촉 객체를
생성·FCStd 저장·재열기해 면 참조 보존을 확인했다. 메시·solver는 실행하지 않았으며
제품 접촉 UI/계산 구현은 아직이다. 전체 작업표의 여섯 진행 상태만 실제 부분 구현에 맞췄다.
후속 Astra 검토에서 두 body의 메시/재생성, 법선·sliding·step의 실제 deck 대응이 빠진
점을 보완했다. Luna는 접촉 압력/침투/마찰 변위의 FRD와 pair 힘의 DAT를 기존 parser에
연결할 위치를 조사했다. 두 출력의 부호/association이 다르며 양수 gap은 FRD COPEN만으로
얻을 수 없어 명세에 미해결 구현으로 남겼다. 넓은 수치 검증은 선행하지 않았다.
다음 실제 Pro 요청 `PRO-IMPL-CONTACT-20261013-01`을 같은 대화에 전송했고 실제
userMessage `01a133bc-eb27-77f4-98b1-455457d0f371`의 본문에서 수신을 확인했다.
기준은 main `08ecb55`의 SPEC-CONTACT-001/FN-14/C05와 관련 기존 native 코드다.
현재 Expert 교정을 게시한 뒤 추가 승인을 기다리지 않고 사용자 모델의 접촉 편집·메시·
해석/Runner·Post 연결을 작성하도록 맡긴다. 새 작성 브랜치는
`codex/contact-workflow-20261013`; Pro가 제품 코드·관련 검사/사용 안내를 쓰고 Codex는
공유 계약 통합·CURRENT_STATE/SPEC/Windows 실행을 소유한다. 첫 접촉 편집/분리 메시
준비 코드 `e916a32`를 main `d5fdcb5`에 통합했다. 실제 FreeCAD 검사에서 preview가 원본
형상의 내부 상태를 바꿔 참조를 무효화하는 문제를 재현했고, Astra가 입력 보존·법선 비교·
suppressed 메시 처리의 세 문제를 찾았다. 같은 Pro의 `PRO-CONTACT-FIX-01` 교정
`37916e8`을 `71f3e03`으로 통합했다. FreeCAD의 형상 복사 API를 사용해 preview를 만들고
표시/취소 때 편집 중인 값을 보존한다. 수정된 접촉/Qt 검사 6건은 통과했다.
실제 FreeCAD 1.1.4에서는 공개 두 발 모델의 여러 면 선택→잘못된 초안 보존→값 수정→
두 물체의 빈 native Gmsh 객체 준비→접촉 저장/재열기까지 통과했다. 형상·접촉·메타데이터는
실제 native 객체이며 GUI 존재/선택 조회만 대역이다. 메시 생성·solver·실제 창 입력 검사는
아직 하지 않았다. 해당 기록은 `runs/product-development/20261013/contact-editor-9e3f7ed8/receipt.json`.
Pro의 export/Runner/Post 연결 `8d350ab`을 `bdc9fb9`에 통합하고 원격 main에 게시했다. 기존 native 면/하중
매핑·접촉 writer, JobManager와 FRD/VTU 경로를 확장한다. 첫 집중 검사16건은 통과했고
3건은 테스트 fixture가 Windows CRLF를 써서 실패했다. 실제 export는 LF를 명시한다.
Astra가 찾은 원 native 세션 종료 뒤 원본 열기 누락, Force 표의 이중 단위 변환,
구속면 변경 뒤 오래된 이름 기반 mesh group을 사용하는 문제를
`PRO-CONTACT-EXEC-FIX-01`로 같은 Pro에 전달했다. 교정 `b19c8f1`을 `6175e90`으로
통합했고 변경된 contact/native export/원본 이동/FEM 단위 검사66건이 통과했다. 실제
FreeCAD의 두 면100N 하중을 내보낸 결과 합력이 -Z100N으로 보존됐고, export는11.484초에
완료됐다. 근거는 `runs/product-development/20261013/contact-export-402e8ca7/receipt.json`.
교정 확인은 Codex의 소스·실행 확인이며 Astra 재검토 통과 주장은 아니다.

이 입력을 실제 CalculiX 2.22와 제품 adapter로 실행해 41.703초에 성공했다. 10개 증분의
변위·접촉 응답과 pair 힘을 읽었고 원 FRD/DAT를
`runs/product-development/20261013/contact-run-0b93d1b2/attempt/`에 보존했다.
Runner 화면을 통한 제출이나 공학적 정확성 승인은 아니다. 실제 ParaView 열기에서는
ASCII VTU의 비유한 GeomGap 값을 읽지 못하는 오류가 발생했다. 별도 native VTK 확인에서
NaN 대소문자 변경은 실패하고, inline binary Float64는 NaN/±Inf를 그대로 읽었다.
같은 Pro의 `PRO-CONTACT-POST-FIX-01` 교정 `5744079`를 `b97ae6b`로 통합했다.
변경 경로 검사10건이 통과했고, 보존된 FRD/DAT에서 별도 Post 파일만 재생성했다.
실제 ParaView는10개 프레임의 모든 PointData를 읽었으며 NaN과 유효성 배열도 보존됐다.
접촉 압력(MPa)과 정적 하중 단계1.0을 선택해 프로젝트를 저장했고 새 pvpython 프로세스에서
같은 선택과3403절점/1654요소를 복원했다. 근거는
`runs/product-development/20261013/contact-post-8096fa28/receipt.json`과 `reopen-receipt.json`이다.
원 계산과 실패한 VTU를 보존했고 솔버는 반복 실행하지 않았다. 마우스 입력이나 공학적
정확성 승인은 아니다. 다음 기능은 이 결과에서 접촉쌍·면을 선택하고 힘/간극/압력 이력을
살핀 뒤 기존 Post 측정과 Numerical로 이어가는 사용자 조작이다. Luna가 native Post의
기존 `bridge.py`/`workspace.py`, Research 측정과 `post_numerical.py`의 Plan 검토/추가
경로를 조사했다. 현재 whole-mesh PVD에는 pair별 선택이 없고 실제 pair 힘 sidecar도
화면/측정에 연결되지 않았다. `PRO-CONTACT-INSPECT-01`을 같은 Pro 대화로 전송했고
실제 사용자 메시지와 새 작업 턴 `01a1340a-8fc3-72ac-8a6e-fd2b2d7446f3`의 진행을 확인했다.
기준은 원격 main `a2ae3f6`이며 Pro의 `5744079`를 포함한다. Pro는 기존 native Post 안에서
pair/면/증분 선택과 압력·간극·힘 이력, 저장/재열기와 선택 응답의 기존 Numerical Plan
추가를 소유한다. Codex는 공통 계약/등록 경계 검토, 최소 Windows 실행과 문서 통합을 맡고
Astra는 산출물의 핵심 의미·사용자 흐름을 독립 검토한다. 새 solver 실행은 맡기지 않는다.

Pro 접촉 검사 산출물 `1edd036`~`50c7340`을 로컬 `7f27e12`~`0ddd758`로 통합했다.
변경된 contact inspection/Qt/native guard/execution 검사33건이24.75초에 통과했다.
기존 FRD/DAT에서 새 inspection bundle25개 파일을 생성·등록하고 native 프로젝트를 열었다.
실제 Show faces에서는 ParaView6.2의 `ColorBy(display, None)`가 초기 association `NONE`을
거부해 실패했다. 별도 native 확인에서 명시적인 empty POINTS association 또는
`SetScalarColoring(None, 0)`는 동작했다. Astra는 bundle 누락 시 partial restore가
제거된 overlay reader를 healthy로 검사해 복구창 진입을 막는 소스 결함도 찾았다.
같은 Pro에 `PRO-CONTACT-INSPECT-FIX-01`로 두 교정을 전송했고 진행을 확인했다.
ColorBy 오류만 우회한 별도 진단에서는 실제 접촉면·10행 힘 측정·저장이 성공했다.
제품 통과로 표시하지 않는다. 새 프로세스 재열기에서 두 Threshold의 SelectedComponent가
저장 전 빈 문자열에서0으로 바뀌는 실제 default 정규화를 추가 확인해 같은 Pro에 전달했다.
다른 graph 차이는 없었으며 생성 시 명시적 설정 등 국소 교정을 요청했다. 실제 결과를
넣은 Qt 결과 창의194개 접촉면 절점·10개 증분 표/곡선도 렌더했다. native 통신은 이 렌더의
검사 범위가 아니며 원본은 `runs/product-development/20261013/contact-inspect-bb998593/`이다.
Pro 교정 `6e22066`을 로컬 `193845a`로 통합했다. 실제 Show faces의 ColorBy 예외는
해소됐으나 native 검사 자체가 ParaView EnumerationProperty를 정수와 직접 비교해
중단됐다. 별도 native 조회에서는 SelectedComponent의 실제 원시 값이0이었다.
수정된 guard 검사9건은 통과했고 새 partial restore 검사는 UTF-8 저장 파일을 Windows
기본 cp949로 읽어 실패했다. 같은 요청의 후속으로 두 검사 코드 교정을 Pro에 전달했다.
검사 교정 `26d3b55`를 `c4fc7b4`로 통합했고 guard10건이0.68초에 통과했다.
제품을 바꾸지 않고 검사 assertion만 원시 native 속성 조회로 바꾼 root helper에서는
접촉면·10행 힘 측정·저장이 성공했다. 새 프로세스 재열기는 여전히 두 SelectedComponent의
저장 전 빈 문자열/복원0 차이로 거부됐다. native 원시 값과 enum label 표현 차이를
안정적으로 기록하도록 같은 Pro에 추가 교정을 요청했다. 입력/솔버 재실행은 없다.
추가 교정 `5cb083c`를 `b6dc2d6`로 통합했다. 접촉 overlay만 원시 integer 속성을 기록하고
기존 일반 분석의 저장 형식은 유지한다. 변경 guard17건이0.82초에 통과했다. 수정 없는
제품과 검사 스크립트로 실제 ParaView6.2의 접촉면 표시→10행 힘 측정→저장 및 별도
새 프로세스 재열기가 통과했으며 restore 문제 목록은 비어 있다. 근거는 같은 실행 폴더의
`checked-enum-inspection.json`과 그 saved 프로젝트다. 기존 실패·진단 저장본은 보존한다.
Astra의 이 공통 속성 처리 변경에 대한 읽기 전용 독립 검토는 추가 구체적 결함을
찾지 않았다. 실행 통과는 root의 결과이며 Astra 실행 주장과 구별한다. 이번 묶음은
`e7c9b32`로 원격 main에 직접 게시했고 원격 SHA 일치를 확인했다. Space의 현행 안내도
이 통합과 다음 CAD/Numerical 배정으로 갱신·재조회했다. 강제 push나 PR 우회는 없다.

병행 조사에서 다음 연결의 실제 빈틈도 확인했다. 현재 Pre 변수 등록은 길이 치수에
한정되고, 접촉 adapter는 이미 고정된 snapshot만 실행한다. 기존 Numerical 후보 저장과
JobManager는 재사용할 수 있지만 사용자 CAD의 후보별 형상/메시/조건 생성과 편집 가능한
FreeCAD 문서로의 명시적 채택이 아직 없다. Astra가 이 후속 설계의 단위·참조 복구·재메시·
실패/취소·원본 보존 경계를 읽기 전용 검토했다. 권고를
[사용자 CAD 후보 계산·채택 명세](.moai/specs/SPEC-CAD-NUMERICAL-001/spec.md)에 반영했다.
형상뿐 아니라 하중·변위·재료·접촉 계수의 typed 변수, 후보별 면 대응/재메시,
binding 실패 이전의 시도 보존, 계산 당시 editable 모델에서 새 분기 열기를 포함한다.
기존 Simulation recipe·Numerical·JobManager·native opener를 재사용하고 pinned worker의
단일 fixture 전체 생성 경로를 일반 사용자 모델로 간주하지 않는다.
`PRO-CAD-NUMERICAL-01`을 같은 실제 Pro에 전송했고 본문과 끝 경계의 수신을 확인했다.
Pro가 `codex/cad-numerical-20261013`을 접촉 교정본 `5cb083c`에서 만들었다. 사용자 CAD
변수→후보 준비/해석→실제 후보 모델의 새 분기 열기를 작성한다. Pro는 제품·관련
검사/사용 안내, root는 현재 상태·SPEC·공통
계약 통합·실행, Astra는 중요한 후보/참조/취소/채택 경계의 독립 검토를 맡는다.
Pro의 첫 구현 `4beca42`를 로컬 `0ff9c5e`로 회수했다. 아직 원격 main에 게시하지
않았다. 변경 단위 검사에서 6건 통과·2건 실패이며 실패는 재열기 검사 호출의
`kind='numerical'` 누락이다. 별도로 실제 Python import에서 Pre bridge의
`RESEARCH_OPERATIONS`/`ResearchInputs` import 누락으로 시작이 실패했다.
`PRO-CAD-NUMERICAL-FIX-01` 교정 요청을 같은 Pro 대화에 전송했고 Astra에
이 첫 구현의 후보·참조·취소·새 설계 채택 경계를 읽기 전용 검토 배정했다.
독립 검토는 시작 import 누락 외에 같은 native target의 이름 변경/중복 등록으로
두 변수가 같은 값을 덮어쓰는 문제와 native FEM에서 바꾼 접촉 정의를 후보가
이전 metadata로 되돌리는 문제를 찾았다. 근거를 확인해 같은 Pro에
`PRO-CAD-NUMERICAL-FIX-02`로 전송했다. FIX-01의 교정 소스는 아래와 같이 회수했고
FIX-02는 공식 전송 도구 접수 후 교정본을 기다린다. 기존 응답을 중단하거나
중복 재전송하지 않는다. MoAI spec_progress도 구현 진행 상태로 다시 조회했다.
Pro의 시작 교정 `945a61e`를 로컬 `c22c0c2`로 통합했고 관련 단위 검사9건이
2.48초에 통과했다. 실제 FreeCAD GUI owner에서 공개 모델 사본의 치수·하중·강제변위·
탄성계수·접촉 강성을 등록하고 `pre.research.prepare`로 CAEPRE 저장까지 확인했다.
`runs/product-development/20261013/cad-capture-ad346f8e/receipt.json`에 성공과 원본
보존을 남겼다. OS 입력·broker·후보 계산·solver 실행·새 설계 채택의 증거는 아니다.
첫 capture 실패는 root helper가 Force 없는 옛 예제를 참조한 것으로 입력을 교정했다.
Windows의 패키지 루트 FreeCAD.exe가 즉시 종료하고 bin/freecad.exe 자식이 남는 것을
확인했다. bin 실행으로 위 capture를 마쳤고, 후보 adapter의 실제 실행 파일 선택과
Windows 자식 Gmsh 취소 범위도 Pro에 교정 검토 요청했다. 기존 종료 helper의
Windows 경로는 leader만 종료하므로 전체 process tree 취소 통과로 표시하지 않는다.
원격 main 확인값은 `b423e37`이다. 첫 소스 회수와 사용 가능한 구현 완료를 구별한다.
후속 Pro `213347c`를 `875ae72`로 통합했다. 등록 이름 변경 시 같은 속성의 기존 등록을
교체하고, 원본 접촉 정의를 변수 적용 전에 검사하며 응답을 종류·단위에 맞는 선택
대화상자로 편집한다. Plan 초기화 중단 후 재시도에서도 사용자 편집을 보존한다.
관련 단위/Qt 검사16건이 11.06초에 통과했고 Astra가 기존 세 지적의 해결과 추가 중요한
회귀 없음으로 읽기 전용 검토했다. 실제 후보 계산은 아직 완료되지 않았다.
첫 실제 후보에서 Stock.Length20→22mm 변경, Bridge의 세 면 대응, 두 body Gmsh
재메시까지 진행됐으나 native 저장 경로에서 실패했다. 후보/편집 사본/실패 결과와
원본 보존은 `runs/product-development/20261013/cad-candidate-e310c69d/receipt.json`에
남겼다. 213 교정본의 짧은 출력 루트 재시도도 freeze에서 같은 실패이며
`runs/cad-candidate-2df98a5f/receipt.json`에 보존했다. solver는 시작되지 않았다.
동일 native 문서의105글자 경로 저장은 성공하고277글자는 OSError로 실패함을 별도로
확인했다(`runs/product-development/20261013/native-save-path-efe074ee/receipt.json`).
후보의 약245글자 경로에서도 실패해 단순260글자 검사만으로는 충분하지 않다.
짧은 native staging과 원래 저장소로의 정확한 보존·Windows 자식 취소 교정을 같은
Pro가 작성 중이다. 이 원인으로 메시/솔버를 반복하지 않고 교정본을 통합한다.
Pro `b9f2a29`를 `a2b37db`로 통합해 실제 bin 실행 파일 선택과 Windows Job 기반
후보 자식 프로세스 수명을 연결했다. 새 검사11건, 영향받은 기존 실행 검사16건
(플랫폼 조건7건 제외), 기존 프로젝트 저장 검사7건이 통과했다. Windows의 실제
표준 Python 자식 취소/무관 프로세스 보존/정상 종료 대기는 확인했으며 Gmsh 취소
실행 자체는 아직 하지 않았다. native 짧은 임시 저장 뒤 긴 목적지로 복사하는 교정은
277글자 목적지에서 embedded Python copyfile이 실패했다. 실제 복구용 임시 사본과
`runs/product-development/20261013/native-save-path-aa145181/receipt.json`을 보존하고
Pro에 교정을 요청했다. 이 상태를 긴 경로 지원 완료로 표시하지 않는다.
실제 FreeCAD Qt6.8.3에서 변수 표와 접촉 압력 응답 선택을 열고 선택값·MPa 단위를
확인했다. `runs/product-development/20261013/native-research-view-ca195863/`에 창
렌더와 receipt를 남겼다. 직접 native 명령 연결이며 OS 입력/전체 broker 왕복은 아니다.
Astra는 `a2b37db`의 Windows Job 소유권·정리 실패 보존·기존 실행 호환·저장 실패
복구를 읽기 전용 검토했고 추가 구체적 지적은 없었다. root가 실제로 확인한 긴 경로
복사 실패는 여전히 미해결이며 독립 소스 검토로 실행 통과를 대신하지 않는다.
후속 Pro `37ac470`을 `a4555ce`로 통합했다. 후보 준비 전체를 짧은 native 작업
폴더에서 수행한 뒤 서비스 Python이 결과를 보존한다. 실제 Windows 후보의 Stock
길이를 20→22mm로 바꿔 메시·freeze·CalculiX 계산·접촉 반력 회수까지 85.782초에
성공했다. 원본은 보존됐으며 [실행 기록](runs/product-development/20261013/cad-candidate-e4e6e508/receipt.json)의
최종 CFN/Z는 324999.7N이다. 이는 실제 실행·응답 전달 확인이며 공학적 검증이 아니다.
같은 계산 후보의 editable.caepre를 새 native 창에서 열면 여전히 Foot contact의
geometry changed 오류가 발생한다. `runs/cad-reopen-e0feb6fe/receipt.json`에
메시/solver 재실행 없이 확인한 실패를 보존하고 같은 Pro에 전달했다. 이전 실패
모델의 별도 짧은 freeze와 target 비교도 `runs/cad-export-871b946b/receipt.json`,
`runs/cad-target-f95ba258/receipt.json`에 남는다. 접촉 참조를 강제로 덮어쓰지 않는다.
새 변경 단위 검사는 14 PASS/1 FAIL이다. 실패는 새 reopen 검사가 workspace 대신
내부 workbench root를 다시 전달한 위치로, Pro에 교정 요청했으며 통과로 계산하지 않는다.
Astra의 `37ac470` 읽기 전용 검토에는 추가 데이터 손실·실행 경로 지적이 없었다.
후보의 저장·재열기 수용, 실제 Plan/broker 전체 왕복은 여전히 미완료다.
Pro `6b274ec`·`300b803`을 `2e85a14`·`96ce9fc`로 통합했고 변경 단위26개가
통과했다. reopen 검사의 workspace 인자 오류를 고쳤고, 실제 보존 모델의 접촉·메시·
변수를 다시 읽어 확인한 뒤 계산한다. 후보 관련 managed 저장에는 FreeCAD binary
BREP를 한시적으로 사용하고 사용자 옵션을 원상 복구한다. 이는 기존 불일치 원인을
확정하거나 과거 실패 모델을 수리한 주장이 아니다. Luna가 보존 사본의 저장 표현을
비교 중이며 실제 native 재열기 수용은 확인 결과로 따로 갱신한다.
별도 native Post→Qt 실제 broker 연결 시도는
`runs/product-development/20261013/contact-handoff-83394326/receipt.json`에 실패로
남겼다. ParaView의 restore 진입 이후 60초 안에 broker 등록이 없어 중단했으며
실제 Qt 왕복 통과로 기록하지 않는다. 기존 pvpython 저장·재열기 통과는 유지하고
이 연결 진단이 CAD 기능 작성을 기다리게 하지 않는다.
Luna가 설치된 FreeCADCmd1.1.4에서 공개 모델 사본의 mapped-element API를 확인했다.
Bridge의 치수/Notch 위치 변경과 저장·재열기에서 두 mapped face가 유지됐고, 사라진 면과
분할 면은 `?Face`/lookup 실패 또는 다중 후손으로 구별됐다. primitive Box에는 map이
없어 FaceN 반환을 이력으로 오인하면 안 된다. 이 실제 관측과 정확한 API를 Pro에
전달했고 [기존 연동 조사](docs/research/OPEN_SOURCE_CONTACT_INTEGRATION.md#native-face-correspondence-for-cad-candidates)에
통합했다. 후보 실행기의 완료가 아니며 메시·solver를 돌리지 않았다.
Pro의 별도 실행 전 검사 수정
`1b37942`는 `02ed0ae`로 통합했다. 두-body contact를 단일 메시 조건으로 잘못 거부하지
않고 기존 export 검사 경로를 재사용한다. 변경된 native API 단위 검사1건이 통과했다.

편집 단계 이후 실제 FreeCAD GUI에서 기존 `pre.fem.mesh_generate`를 호출해 두 물체의
Gmsh 메시를 생성·저장했다. Base1147절점/532요소, Bridge2256절점/1122요소이고 접촉
참조 진단은 비어 있다. `runs/product-development/20261013/contact-mesh-350b4d63/receipt.json`과
`contact-meshed.FCStd`에 남겼다. 마우스·키보드 입력이나 solver 검사가 아니다. 앞선
FreeCADCmd 시도는 Qt 비동기 대기와 없는 ViewObject 때문에 실패했고 GUI 경로로 확인했다.
그 실제 메시 사본에 재료·Base 지지·Bridge 상면의 -0.3mm 강제 변위를 적용해 새 native
contact export도 완료했다. 설치된 writer와의 입력 비교, editable FCStd·mesh·deck·manifest를
`runs/product-development/20261013/contact-export-bf12e0c8/`에 보존했다. 예제 설정이며 물리
정확성·solver 실행의 증거가 아니다. 공통 FRD reader의 변경 영향 검사34건과 추가 FEM Qt
4건도 통과했다. 첫 export는 수분이 걸렸으며 요소마다 native.Nodes 전체 사전을 반복해서
읽는 기존 quality 경로를 확인했다. 같은 호출에서 절점표를 한 번 읽는 Pro 교정을
통합해 위의11.484초 export를 확인했다. 원래 측정이 정밀한 성능 benchmark는 아니므로
배율 개선을 주장하지 않는다. 수치 기준을 생략하거나 넓은 benchmark를 선행하지 않는다.
사용자 추가 지시에 따라 기존 오픈소스 전후처리기·solver 연동 코드와 이슈를 병행 조사해
현재 구현에 적용한다. [기존 연동 코드·이슈 조사](docs/research/OPEN_SOURCE_CONTACT_INTEGRATION.md)에
PrePoMax의 면/접촉 법칙 분리와 writer, ccx2paraview의 시간 이력 변환과 누락값·NaN을
0으로 만드는 처리, FreeCAD의 다중 메시 제약을 정리했다. 기존 converter의 재사용과
현재 reader 확장을 비교해 실제 부족한 연결만 구현한다. GPL을 무료 재사용 배제 이유로
삼지 않으며 배포 조건은 선택한 방식에 맞춘다. 조사 때문에 제품 작성을 중단하지 않는다.

접촉 구현의 실제 입력으로 [두 발 CAD 예제](examples/contact/README.md)를 추가했다.
FreeCAD의 편집 가능한 Boolean 형상이며 두 접촉면·0.2 mm 간극·받침을 저장/재열기했다.
이 추적 예제 자체는 입력 형상이며 생성된 접촉 선언·메시·계산은 위의 실행 기록에 따로
보존한다. 설치된 `ccx.exe -v`는 2.22를 반환했다.
Pro는 물체별 메시를 생성하고 export에서 절점/요소 번호를 분리하는 구현 방향을 선택했다.
Astra는 원본 물체 메시에서 면/하중을 먼저 매핑하고, 합칠 때 총하중·재료 배정과 역매핑을
보존해야 한다고 검토했다. 이 조건을 Pro에게 전달했으며 별도 solver 검증을 선행시키지 않는다.
실제 데스크톱 캡처는 Windows 잠금 화면이어서 해제를 요청했다. 창 입력 확인만 대기하며
Pro 작성과 코드 통합은 계속한다. 공개 PDF/Markdown/CSV의 첫 자료 가져오기 예제도 준비했다.
첫 통합 경로는 CAD/FE→Simulation→Runner→native Post→최적화와
Expert→Numerical→결과→Study이며
Data/Material/PDE는 독립 병행한다. 별도의 개발 시작 문구를 기다리지 않는다.
사용자는 [검토 안내](docs/design/20261012-desktop-planning/REVIEW_GUIDE.md)의 화면과
Qt 조작에 피드백을 줄 수 있다. 이를 반복 인터뷰나 과거 solver 전수 검증으로 바꾸지 않는다.
화면 수용과 지원 backend/장비/Expert 무료 연결은 해당 기능의 사용자 검토·기술 확인에
연결된 미완료 항목으로 유지한다.
현재 시제품은 정밀 입력·저장·재열기·선택·도킹 등 Qt 조작을 확인한 planning source다.
native OS/DPI·실제 FreeCAD/ParaView 연결·solver/provider/device는 미확인으로 남는다.
기획 요청의 원요구52개 추적표는 TRACED_NOT_IMPLEMENTED_BY_THIS_REQUEST를 보존한다.
새 기능 구현 현황은 해당 SPEC과 실행 기록에서 판단하며 원요구 전체 완료로 확대하지 않는다.
과거 수치 실패·UNKNOWN과 원 허용치는 그대로 유지한다.

### 다음 Expert 구현 배정

`PRO-EXPERT-CONNECTION-01` 전송·수신 확인: 같은 실제 Pro 대화에 CAD 교정 체크포인트 후
독립 Expert의 연결·모델·기존 역할 선택 화면을 맡겼다. 수신 메시지는
`01a1352f-67f8-73a0-b324-812c14c09616`이다. 기준은 Pro `37ac470`, 로컬
`a4555ce`이며 [SPEC-EXPERT-002](.moai/specs/SPEC-EXPERT-002/spec.md)를 따른다.
Luna의 읽기 전용 조사에서 Ask→기존 runtime, 제안→Numerical, 결과→원 Expert/Study는
이미 연결돼 있었다. 이를 재구현하지 않고 아직 없는 native 설정 진입을 완성한다.
Windows의 기존 OpenScience profile marker/config와 runtime binary는 존재한다.
인증·구독 사용 가능 여부는 별도이며 설정 확인만으로 모델을 실행하지 않는다.
Pro는 제품·관련 테스트·사용 안내를 작성하고 Codex는 SPEC·실행·통합을 소유한다.
현재 CAD 전달과 같은 대화에서 순차 작성하며 공유 파일에 병행 작성자를 두지 않는다.
Pro는 `300b803`에서 `codex/expert-connection-20261013`을 만들고 연결 UI 작성에
착수했다. Astra가 확인한 native Windows의 `wslpath` 의존, 질문 전송의 별도 operator
허용, cached assistance/config 변경의 실제 적용 문제도 같은 Pro에 전달해 SPEC에
포함했다. 파일 저장이나 모델명 선택만으로 연결 완료 처리하지 않는다.

### 앞선 통합 기록

사용자는 Codex와 실제 ChatGPT Pro가 문서 정리와 작업 방식을 토론해 **확정하고 반영**하도록
지시했다. 제안·상태 보고만 반복하거나 일상 반영을 위해 다시 승인을 기다리는 단계가 아니다.
맡긴 현행 문서/진입점 정리, Pro/Codex 책임 확정, Space 안내와 Git 기준 연결은 **완료**했다.
문서 통합 커밋 `6b0c2ed14f9d61204cabfe3c47288f2438202798`을 원격 main에 게시하고
같은 SHA를 확인했다. 관련 Space 6개 Page의 갱신·본문 재조회·기존 첨부 보존도 확인했다.
앞선 통합에 남은 문서 승인이나 제안 확정 단계는 없다. 아래 제품 방향의 본구현은
2026-10-12 당시 상세 기획 검토와 개발 시작 지시를 기다렸으며, 현재 배정은 위의
2026-10-13 기능 단위 구현이다.

다음 제품 작업은 아래 **독립 도구군의 실제 작업 완성**으로 확정한다. 특정 C3D10 메시나
F05 진단을 전체 제품 개발의 우선 과제 또는 선행조건으로 두지 않는다. 제품 구현 자체를
완료로 선언하거나 원래 수치·물리 요구를 없애는 결정은 아니다. 이번 문서 정리 중 새 제품
구현·native 계산·provider 실행은 시작하지 않았다.

## 기준 버전과 근거

- 검토한 기준: `b3fa9188490ea42399974ae07c10e83521f14d1d` (문서 정리 전 main).
- 제품 통합: [PR #7](https://github.com/pikachu444/autonomous-cae-lab/pull/7),
  merge `92a51fd7967ba1127b5a56755ebef6a46f41f04e`. 사용자는 알려진 F05 실패를
  이 개발 통합에 대해 수용했다. 병합 전 진단을 다시 선행조건으로 되살리지 않는다.
- 실제 확인한 CI: source `385818bab785bfbf2c1e5880371970e475c90d68`,
  [run 38159523618](https://github.com/pikachu444/autonomous-cae-lab/actions/runs/38159523618),
  9 jobs pass / Code_Aster failure. 원 측정과 제한은
  [정확한 실행 기록](benchmarks/records/20261012-stabilization-s5-ci-native-continuation.json)에 있다.
  뒤의 문서 커밋과 병합은 새 solver 검증이 아니다.
- pinned upstream: `3e48bf6138f495299f45b1af254bfb4aaff307b8`.
- 아래 현황은 해당 코드와 기존 실행 기록을 대조한 것이다. 이번 문서 정리에서 새 GUI·
  solver·실제 AI 계산을 실행한 것으로 읽지 않는다.

## 전체 제품 현황

전체 구성은 FreeCAD CAD/FE, ParaView Post, 독립 Research 도구와 선택 Workbench로
정해져 있다. 상당한 구현과 부분 실행 근거가 있으나 전체 제품·사용성·배포는 미완료다.
구성·기존 구현을 재사용하되 최신 요청의 상세 화면·사용성 기획은 다시 검토한다.

| 영역 | 현재 구현/근거 | 남은 주요 제품 작업 |
|---|---|---|
| CAD/FE Pre | native 치수·Assembly·FEM 명령, 관리형 저장, 지원 계산 제출, 결과/원 설계 이동 | 실제 사용자 모델의 편집·선택·오류 복구·저장/재개를 포함한 전체 화면 작업. 넓은 접촉·비선형 지원은 별도 범위 |
| Post | 외부 결과 열기, 필터·측정·지원 비교, Apply/Undo, 원자료 수리, 부분 저장·재열기. 실제 ParaView의 제한된 실행 근거 | 실제 화면에서 대상·필드·위치·시간을 다루는 작업, 지원 비교 범위와 도구 이동 |
| Data | CSV/NPZ, 채널·축·단위·매핑·구간/mask, 보존 응답 비교, 실제 HTTP/Qt 저장·재시작 | 표·그래프 연동 선택, 처리 정의 편집과 큰 자료의 조작성 |
| Material | FELUPE 및 일부 MFront 법칙, 계수·이력, 평가·보존 응답·Plan/채택 연결 | 법칙·시험·관측·계수·상태 연구의 화면과 범용 protocol/FE 연결. 대역 UI 검사는 실제 native 물리 수용과 구별 |
| PDE | 선언된 모델의 편집·지원 검사·평가·보존 결과와 Post/Plan 이동 | 식·영역·조건·결과의 편집 깊이와 일반 ODE/약형식·solver 설정 등 지원 범위 |
| Numerical / Evaluation | Material/범용 Request Plan, 변수·응답·방법·후보·채택, 단계/전달/반복 정의와 일부 실제 수치/연성 실행 | 내부 key/value 중심 편집 개선, 방법별 의미·결과 해석, 지원 조합·재개 범위 |
| Runner | 실제 job 입력·상태·진단·취소·결과와 원 문서/Post/Study 이동 | 실제 배포 환경의 실패·취소·재접속·장시간 실행과 도구 이동 |
| Expert | 역할·논점·reply·개입·pause/resume·근거·Plan, 실제 provider/callback 기반. 이전 웹 화면의 실제 연구 왕복 기록 | 새 독립 Qt 화면의 자료/모델 설정부터 실제 대화→계획→계산→결과 후속 논의까지 연결·확인 |
| Study / 선택 Workbench | 질문·가설·근거·판단과 참조/도구 이동 | 별도로 계획한 문서·연결 그래프, 개정·변경 영향 화면. 기존 서비스 이름은 이 UI의 완성 근거가 아님 |
| 공통 GUI/CLI/Python/MCP | 같은 HTTP 서비스·문서 owner·명령·결과, native 명령 경로 | 실제 열린 native GUI와의 교차 작업, 지원 기능 노출과 클라이언트 사용 |
| 설치/독립 실행 | 기본 CMD의 native Qt Runner 진입, Research 도구별 직접 실행, 저장 문서와 같은 서비스 재사용을 구현·확인 | 전체 배포 패키징, 모든 파일 연결·복구와 여러 창의 종료/재실행 사용성 |

코드 위치는 `apps/desktop_pre`, `apps/desktop_post`, `apps/research`,
`caelab/workbench*`, `caelab/adapters`, `scripts/start_cae_research.ps1` 및 기존
설치/실행 스크립트다. [실행 기록](docs/WORKBENCH_PROGRESS.md)의 S1/S2와 후속 교정에서
이미 고친 Pre/Post Save, 초안, 선택·응답 읽기 결함을 새 미해결 과제로 복사하지 않는다.

## 진행 중인 제품 구현 방향

**목표:** 사용자가 원하는 독립 도구에서 자기 자료·모델을 열고 주요 편집과 필요한 계산을
수행하며, 같은 개정·결과를 다른 도구에서 이어 보고, 저장·종료 후 다시 연구를 계속한다.
제품 작성자는 Pro, 독립 검토·환경 확인·통합은 Codex가 맡는다.

진행할 범위:

1. 기존 실행 helper를 제품 진입에 연결한다. 도구·문서 선택, 올바른 창 열기, 서비스
   시작/재접속, 저장 후 새 프로세스 재열기를 완성한다. 계산 backend가 없어도 독립적인
   자료·문서·기존 결과 읽기는 계속 가능해야 한다.
2. Data·Material·PDE·Numerical의 주요 편집을 각 작업의 표·곡선·모델·변수/응답 중심으로
   보완하고, 기존 Pre/Post native 작업과 Runner를 연결한다. 내부 JSON/key를 사용자가
   알아야만 대표 작업을 끝낼 수 있는 부분을 남기지 않는다.
3. Expert에서 자료·모델·역할을 고르고 실제 대화와 개입을 진행한다. 제안된 Plan을
   사용자가 편집해 실행하고 실제 결과를 읽어 후속 논의를 이어간다. 이전 provider와
   공통 도구 구현을 재사용한다. 새 단독 화면의 실제 전체 흐름은 별도로 확인한다.

독립된 도구 보완은 병행할 수 있다. 모든 backend 설치, 선택 Workbench 그래프,
전체 원요구 재감사, C3D10 비교 수정이 다른 도구의 착수를 막는 전제는 아니다.
범용 구성식·PDE·연성·접촉·외부 solver 등의 확장은 제품 범위에 계속 남긴다. 이번
작업의 지원 범위를 명시하면서 확장하며, 첫 연결의 완료를 전체 물리 범위 완료로 바꾸지 않는다.

사용자 관점의 완료 기준:

- 원하는 도구로 직접 들어가 자기 파일/문서를 열고 대상과 관련 설정을 실제로 편집한다.
- 지원 입력은 실제 평가/계산과 결과로 이어지고, invalid 입력은 고칠 위치를 알려 주며 실행을 막는다.
- 다른 도구로 이동해도 같은 문서·개정·선택 결과를 사용한다. 과거 결과는 바뀐 입력과 구별해 남는다.
- 저장·닫기·새 프로세스 재열기 후 편집 내용, 결과와 연구 맥락이 이어진다. 누락 파일·실패·취소는 복구 가능하게 설명한다.
- Expert는 실제 provider와 도구 결과에 근거해 논의한다. 대역 답변·고정 숫자·옛 웹 검증으로 새 화면의 완료를 대신하지 않는다.
- 설치 후 시작/재실행 안내가 실제 동작과 맞고, GUI·CLI·Python·선택 MCP의 지원 범위가 일치한다.

Pro에게는 이 절과 제품 계획·관련 코드의 동일 기준 버전, 미반영 사용자 결정·산출물,
실제 확인 범위를 함께 전달한다. 이번에는 전체 기능과 화면/상태에 연결한 개발 명세와
구현 작업표를 보완한다. 기본 문서 소유와 native 재사용 경계를 임의로 교체하지 않는다.

## 문서와 새 세션 운영

현행 계획·상태·협업은 Git, 사용자 결정·이유·원자료는
[Space](https://chatgpt.com/space/page_6ac6e5e8d7688191a58c5760fda2d2d9)에서 보존한다.
Codex가 의미 있는 변경의 관련 Page 요약/링크까지 맞춘다. 자동 동기화는 없다.
최신 사용자 결정은 Git 반영 전에도 유효하다. Pro와 Codex는 각각 새 세션에서 같은
기준 자료로 작업하며 [시작문](CODEX_START.txt)과 [운영 규칙](docs/CODEX_WORKFLOW.md)을 쓴다.

현재 미반영 제품 코드 산출물은 없다. 앞선 Pro 대화는 문서·우선순위 결정이며 새 구현이
아니다. [실제 Pro 협의](https://chatgpt.com/c/6acc2538-ed3c-83ee-8e6b-6b98c52ea109)를 출처로 남긴다.
기존 `.codex-remote-attachments/`는 사용자 로컬 untracked 자료로 보존한다.
새 세션은 현재 프로세스·설치·인증·ignored 산출물의 존재를 다시 확인하며 가정하지 않는다.

문서 반영 확인(2026-10-12): 원래 52개 ID/설명 일치, 보존본 3개의 Git 저장 바이트와
SHA256 일치, 새 로컬 문서 링크, `git diff --check`를 확인했다. 제품 코드는 바꾸지 않았다.
Page 저장본은 [제품 입구](https://chatgpt.com/space/page_6ac6e5e8d7688191a58c5760fda2d2d9) 13,
[제품 설계·원문](https://chatgpt.com/space/page_d99abd5a046c8191b16263e448c8d8ee) 19,
[결정 기록](https://chatgpt.com/space/page_6ac6e6a501508191913070f4ef51eae9) 7,
[이전 상세기획](https://chatgpt.com/space/page_6ac6e67d6efc8191af147db299b3cf3b) 13,
[검토 원자료](https://chatgpt.com/space/page_6ac79c9b17c48191a63e2775c75fa1d2) 5,
[화면 도면](https://chatgpt.com/space/page_e314876e22bc8191b562de881de7f3b6) 24다.
수정 대상 외 본문과 첨부 참조를 보존했다. 확인 범위는 저장본문과 참조이며 앱 미리보기
요청은 응답하지 않아 렌더링 검토를 추가로 주장하지 않는다.

## 남겨 두는 수치·공학 한계와 기록

F05 원 측정 `3.32295e-6 > 1e-6`과 별도 실패한 AMD 시도는 그대로 남는다. 해당 실패를
이번 문서 정리나 PR 병합으로 통과시키지 않는다. 알려진 실패는 필요한 후속 수치 작업에서
다루며 전체 앱 구성의 선행조건으로 재시작하지 않는다. 물리·재료·강도·내구·회사 배포
승인은 별도이며 UNKNOWN/NOT_RELEASED를 유지한다.

이전 상세 상태/인계는 [보존 원문](docs/history/20261012-before-consolidation/README.md),
실제 실행은 [WORKBENCH_PROGRESS](docs/WORKBENCH_PROGRESS.md),
[PREPOST_VERIFICATION](docs/PREPOST_VERIFICATION.md), `benchmarks/records/`에서 찾는다.
원시 CI ZIP/로컬 runs는 Git clone에 포함되지 않으며 보존 기한과 위치는 해당 기록에 있다.
