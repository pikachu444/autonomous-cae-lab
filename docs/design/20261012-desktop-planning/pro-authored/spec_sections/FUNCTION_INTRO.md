# Autonomous CAE Lab — 전체 기능 상세 명세 D1

요청 ID **PRO-DESKTOP-DESIGN-20261012-01** · 작성 2026-10-12 · 제품 개발 전 검토용.

이 문서는 Pro가 작성한 연결된 whole-product draft다. 기준 코드는 `9a6e3083037630b45694b812b135dc1cd63cf95a`, upstream은 `3e48bf6138f495299f45b1af254bfb4aaff307b8`이다. 실제 조회 범위는 `SOURCE_EVIDENCE.md`와 검토 기록에 한정한다. 전달된 일곱 문서의 최신 사용자 지시가 공개 pin의 옛 “다음 구현” 문구보다 우선한다. 현재 배정/통합 상태의 권위는 기존 CURRENT_STATE에 남으며 이 폴더는 그 파일을 변경하지 않는다.

## 1. 제품의 완료 단위

완료 단위는 사용자가 자료나 모델을 열어 편집하고, 필요한 계산 또는 보존 결과를 확인하고, 실패를 복구한 뒤 저장·재개하는 작업이다. R01–R52는 추적 번호이며 동일 크기의 기능·시험·완료율이 아니다. 구현 대상과 실제 현재 지원은 각 기능 안에서 구별한다. 미지원 backend의 입력 초안도 편집·저장할 수 있고 해당 실행만 차단한다.

Data/Material/PDE/Numerical/Runner/Expert/Study에는 각각 독립 시작과 문서가 있다. Simulation과 Evaluation도 기존 독립 editor를 사용한다. Workbench는 문서 연결의 선택적 보기다. CAD를 요구하는 작업만 FreeCAD에, 복잡한 field 후처리만 ParaView에 연결한다. AI 없이 수행하는 연구에 provider 로그인·MCP·Discussion·Study 생성을 요구하지 않는다.

| 사용자 | 끝내려는 판단 | 주요 진입과 산출물 |
|---|---|---|
| 시험·재료 연구자 | 자료의 물리 의미를 맞추고 후보 law를 구별하여 계수 개정 또는 보류 | Data → Material + 같은 Plan → 보존 예측/잔차/holdout → Material 개정 → Study 판단 |
| 구조·제품 설계자 | 자기 모델의 치수·조립·하중 전달을 바꾸고 기준안과 비교 | FreeCAD Pre → 같은 Runner → ParaView Post → 원 설계 새 개정 |
| PDE·구성모델 연구자 | 식·이산화·적분·연성 정책의 결과와 오차를 구별 | PDE/Material/Evaluation 독립 실행 → field/접선/잔차/기준 비교 |
| 수치 연구자 | DOE/역문제/최적화/UQ/대리/MOO의 실제 후보·실패·불확실성을 분석 | Numerical의 재사용 Plan·engine → 후보·정확 입력·응답 → owner별 채택 제안 |
| 실험 담당자 | 장비·교정·장착·시편 조건을 가진 측정과 예측의 불일치를 설명 | Data·Post → 동정/holdout → Study의 명시 판단·다음 시험 |
| 연구 책임자 | 어떤 근거가 어느 가설을 지지하는지 감사·재현 | Study/Expert → 정확한 문서·result·발언 → 보고서·UNKNOWN/NOT_RELEASED |

## 2. 변하지 않는 책임과 수명

| 소유자 | 소유하는 변경 | 소유하지 않는 변경 |
|---|---|---|
| Core | 공통 ID/record/schema, mapping 계약, gate, artifact/evidence/provenance, 저장·명령 envelope | solver 카드/임의 CAD 식/후보 생성 알고리즘 |
| Domain owner | 물리·단위·입출력 의미와 해당 문서의 draft/변경 이력 | 다른 domain의 최신값 자동 채택 |
| Adapter / native host | 지원 native 구문·객체·경로·실제 UI 주 스레드 호출 | 자체 대체 연구 모델이나 새 일반 scheduler |
| Data | 원자료 참조·채널·단위/quantity 변환·품질/연산 mask·처리 recipe | Plan의 학습/holdout·검색 가중치 |
| Material | law·계수 현재값·protocol·초기상태·적분 설정·직접 결과 | Plan 범위/시작값/탐색 정책 |
| Numerical Plan | 정확 source/evaluator ref, 변수 시작값/범위·관측·목표·예산·후보 선택 | 원 Material/CAD/PDE 값을 선택만으로 덮어쓰기 |
| Evaluation (기존 kind=`evaluation`) | 1–32 단계·전달·반복 정책과 frozen definition | 물리 계수·내부 solver 정책·새 optimizer |
| Runner | 입력 고정·자원·job/attempt·로그·취소/실제 종료 | 물리 증분/수렴 정책 편집 |
| Study / Discussion | Study의 질문·가설·채택 판단 / Discussion의 논점·발언·reply | 새 발언이나 결과의 자동 연구 판단 채택 |
| Post | reader/pipeline·측정·비교 recipe·보기·보존 파생 결과 | 원 field 파일 편집, 미검증 대응의 물리적 정당화 |

`cell buffer → acknowledged owner draft → saved revision → frozen execution input → retained result`는 서로 다른 상태다. 하나의 “저장됨/완료” 표시로 합치지 않는다. 각 기능의 화면 ID는 `screens/screens.json`의 실제 state board와 연결된다. 화면은 선택한 합성 예시이며 native/solver/provider 실행 증거가 아니다.

## 3. 기존 코드와 새 변경의 해석

`IMPLEMENTATION_BACKLOG.csv.current_status`는 확인한 코드의 존재와 제한이고 `implementation_status`는 이번 요청에서 본구현을 하지 않았다는 상태다. `SOURCE_VERIFIED`도 Windows 설치·수치·사용성 PASS를 뜻하지 않는다. 기존 T번호의 “owner 신규” 문구는 현재 존재하는 owner/editor의 재사용·확장으로 수정한다. 기존 Data/Material/PDE/Study/Evaluation, native bridge, JobManager와 numerical engine을 재작성하는 과제는 만들지 않는다.

순서는 각 기능의 실제 입력/저장/실행 의존성으로 정한다. 공통 편집·저장 최소 계약과 도구별 UI를 함께 진행하고, solver 후보 전체 설치·옛 F05·Material 완료·Workbench/AI 연결을 독립 작업의 전역 선행조건으로 삼지 않는다. 본구현 착수는 이 시안 검토 뒤 사용자의 개발 시작 지시를 기다린다.

## 4. 상태와 정확성의 표시

| 축 | 화면에 나타낼 값 | 결론의 한계 |
|---|---|---|
| 편집 | BUFFER / DRAFT DIRTY / SAVED rN / SOURCE CHANGED | 저장된 revision과 현재 입력의 동일성 |
| 실행 | NOT_SUBMITTED / QUEUED / RUNNING / CANCEL_REQUESTED / terminal | 프로세스·명령 수명; 취소 접수는 종료가 아님 |
| 결과 | VALID / PARTIAL / INVALID / NOT_EVALUATED / NOT_RETAINED / NOT_CONVERGED | 실제 응답 사용 가능성; penalty와 물리값은 별도 |
| 환경 | REGISTERED / NOT_PROBED / 해당 검사 receipt / UNAVAILABLE | 선언 capability와 실제 확인 범위 구별 |
| 근거·release | UNKNOWN / NOT_RELEASED 및 검사별 상태 | 실행·UI·수치 검증이 실제 공학적 승인으로 승격되지 않음 |

과거 실패·원값·threshold와 기존 결과는 보존한다. **F05 `3.32295e-6 > 1e-6`**을 바꾸지 않고 전체 기획 gate로 사용하지 않는다. 빈 값/실패/영역 밖/0분모를 숫자 0으로 채우지 않는다. 로그와 실패 후보도 정확한 출발 입력·attempt와 함께 연다.

## 5. 사용 방법

기능별 절은 실제 start→end를 기술한다. 구현자는 기능 절, 상세 계약 부록, 동일 화면 ID의 `SCREEN_SPEC.md`/JSON, 관련 backlog 행을 함께 읽는다. `VERIFICATION_PLAN.md`는 계획 대조·Qt 조작·구현 회귀·수치 기준·최종 Windows 통합의 시점을 분리한다. `PROTOTYPE_SCENARIOS.md`는 사용자가 검토할 클릭 경로다. 미확인 도구와 비용/라이선스 판단, 기존·신규 Astra 지적의 교정은 `DECISIONS.md`에 둔다.
