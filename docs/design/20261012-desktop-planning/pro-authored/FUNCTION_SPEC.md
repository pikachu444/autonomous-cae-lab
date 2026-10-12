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


## 기능별 상세 명세


### FN-01 — 독립 도구에서 자료를 열고 같은 문서를 다시 찾기

**사용자 / 완료 결과:** 자료 분석자·CAE 엔지니어·연구자 · 도구 바로가기 또는 파일에서 시작해 자기 문서를 정확한 편집기로 열고 종료 뒤 이어서 작업한다.

**추적:** R12, R13, R21, R33, U§1, U§5 · 기존 T02, T03, T04, T02b · UC10, UC15, UC17

**시작 조건:** CAD·AI·Workbench 없이 Research 도구를 직접 실행한다. 서비스가 없으면 기존 launcher가 같은 사용자/store로 시작한다. 최근 파일 목록은 실제 존재·권한을 다시 확인한다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. HOME-EMPTY | 도구 이름, 최근 문서 이름·종류·위치·마지막 저장 시각. 내부 ID 입력칸은 없다. | Ctrl+O로 파일을 선택하거나 새 Data/Material/PDE/Plan/Study를 만든다. 필요한 owner로 바로 진입한다. |
| 2. HOME-EMPTY | 기존 store와 같은 문서가 이미 열린 창, 별도 사본 여부. | 같은 store/document는 기존 창 활성화가 기본이다. 새 view는 같은 owner에 붙인다. 다른 store의 같은 ID는 별개 namespace로 표시한다. |
| 3. DATA-EDIT | 문서명, 현재 입력과 saved revision, dirty 표식, 마지막 결과. | 지원 입력을 편집한다. missing backend가 있어도 문서 읽기·draft 저장은 계속된다. |
| 4. RECOVERY-REOPEN | 마지막 저장본과 복구 가능한 working draft의 차이, 원인과 기록 시각. | 저장본 열기 또는 복구 초안 이어가기를 선택한다. 열기만으로 계산·LLM을 실행하지 않는다. |

**입력·단위·종속 조건:** 열기 대상은 기존 store/document.json, 관리 .caepre, 지원 native/결과 파일이다. 포맷 판별은 내용+버전으로 하고 확장자만으로 owner를 추정하지 않는다. 상대경로·한글·공백·읽기전용·새 버전을 고려한다.

**저장·출력·재열기:** 기존 documents/<ID>/working.json, document.json, revisions/<R>/ 구조와 .caepre/PVSM·native 원본을 유지한다. ‘이동용 사본 저장’은 최소 필요 의존 세트를 새 폴더로 복사하고 기존 manifest를 보존한다. 새로운 .caelab 포맷은 도입하지 않는다. 복사본에서 계속 편집할 때 새 document ID를 부여하고 derived_from으로 출처를 남긴다.

**오류·취소·복구:** 없어진 최근 파일은 회색 행+‘위치 찾기’로 남긴다. 새 포맷은 읽기 전용으로 가능한 결과를 연다. 서비스 연결 실패는 재연결·다른 이미 설정된 store 선택을 제공한다. 문서 열기에 backend probe·최적화·AI 로그인은 붙이지 않는다.

**현재 코드의 재사용:** apps/research/desktop.py의 launch_tool/open_saved_reference/open_origin, scripts/start_cae_research.ps1, 종류별 owner와 client.document_open을 재사용한다. 현재 공개 open은 document_id로 reopen하며 파일 UX와 store 이동은 확장이다.

**추가·변경과 연결:** Research 파일 선택·최근 문서 모델, 기존 프로세스 활성화, store 식별, 파일 종류 dispatch를 보완한다. Windows 파일 연결은 기존 문서/프로젝트 선택에 맞춘다. 기존 root launcher의 웹 기본 진입 변경은 본구현 과제다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. 독립 열기·최소 저장은 각 owner의 기존 계약만 필요하다. native 종류는 해당 native runtime 설치가 필요하며 다른 도구의 선행은 아니다.

**사용자 완료 조건:** 새 Windows 프로세스에서 자기 Data와 Material, CAD 없는 PDE, 독립 Study를 열고 편집한다. 같은 문서의 이중 writable owner를 만들지 않는다. 재열기 시 결과 ID와 원 입력이 유지된다.

**검증 연결:** PV-01 planning → UI-01 Windows 파일·창 → RG-01 same owner → IT-01 cold reopen.


### FN-02 — 셀 편집·동시 dirty·충돌·부분 저장을 잃지 않고 처리

**사용자 / 완료 결과:** Material와 Plan을 한 창에서 편집하는 엔지니어 · 어느 문서를 바꾸고 저장했는지 알고, 다른 client의 변경과 저장 실패에서도 자신의 입력을 복구한다.

**추적:** R08, R11, R12, R13, R19, R20, U§6 · 기존 T02, T03, T18, T19 · UC01, UC09, UC17

**시작 조건:** Material r17와 Plan r8을 한 화면에 열고 현재값은 Material, 범위·fit 역할은 Plan의 같은 owner로 편집한다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. MAT-DIRTY | 상단 Material * / Plan * 두 표시, 선택 셀의 owner, 입력중 ‘1e’와 owner에 반영된 0.85 MPa. | Enter는 셀 버퍼를 해당 owner draft에 제출하고 Esc는 버퍼만 취소한다. 숫자 오류는 문자열 draft와 셀 진단으로 저장 가능하게 보존한다. |
| 2. CLIENT-CONFLICT | 내 기준 generation 41, 서버 42, 같은 coefficient의 이전/내 값/다른 client 값. | 내 변경 복사·원본 다시 읽기·새 분기 중 선택한다. 겹치는 셀은 자동 병합하지 않는다. non-overlap도 fresh preview 후 명시 적용한다. |
| 3. SAVE-PARTIAL | Material r18 저장 성공, Plan r8→draft 저장 실패, 아직 갱신하지 않은 연결. | 실패 파일·경로를 수정하고 Plan만 다시 저장한다. 성공한 Material r18을 되돌리거나 전체 성공 알림을 내지 않는다. |
| 4. CLOSE-DIRTY | 셀 버퍼·owner draft·saved revision 3열, 열린 job의 계속 실행/취소 항목. | 선택 문서 저장 후 닫기, 초안 복구본 유지 후 닫기, 계속 편집을 고른다. ‘닫기’와 job 취소는 별개다. |
| 5. RECOVERY-REOPEN | saved Material r18, Plan r8 및 복구 draft, 마지막 저장 관계. | 새 owner에서 저장본/복구본을 구분해 연다. 미완료 save group은 재개 또는 해제하며 기존 refs는 그대로다. |

**입력·단위·종속 조건:** 변경은 document_id+store+session+expected_generation+command_id를 가진다. saved revision과 input revision은 다른 값이다. UI focus/selection은 계산 입력 generation을 올리지 않는다. 붙여넣기 대상 owner별 patch를 미리 표시한다.

**저장·출력·재열기:** 기존 append-only revision과 mutable publication pointer를 재사용한다. 새 save-group receipt는 ‘각 owner 저장 결과와 연결 게시 여부’만 기록한다. 모든 owner를 새 transaction framework로 이관하지 않는다. 준비·복사 실패는 이전 pointer 유지; 일부 owner 이미 게시한 경우 그 성공과 실패를 정직하게 남긴다.

**오류·취소·복구:** Ctrl+Z는 마지막 편집 owner와 명령명을 메뉴에 표시하고 그 owner의 Undo를 호출한다. 적용 전 셀 Esc는 Undo stack을 바꾸지 않는다. 서버가 변경되면 stale patch를 재전송하지 않는다. 서비스 연결이 끊겼을 때 로컬 편집 복구본은 저장할 수 있으나 owner 저장 완료로 표시하지 않는다.

**현재 코드의 재사용:** MaterialDocuments.command/_changed/_save의 generation·command receipt·append-only 저장과 기존 각 window의 apply/save/refresh/close 경로를 재사용한다. 원자적 publication은 이미 있어 이를 신규 결함으로 다시 만들지 않는다.

**추가·변경과 연결:** 같은 PlanVariablesTable을 Material에 embed하고 owner 표시·공통 cell delegate·related save coordinator를 추가한다. UI buffer와 acknowledged draft를 구분하며 동시에 열린 창끼리 draft 상태를 전달한다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. FN-01. 개별 owner 저장을 먼저 유지하면서 연결 저장을 추가한다. 두 owner의 schema를 동시에 다른 agent가 바꾸지 않는다.

**사용자 완료 조건:** 숫자를 입력하는 중 외부 변경·부분 save·close를 발생시켜도 입력 소실과 결과 바꿔치기가 없다. 새 프로세스에서 saved/draft/refs를 구분하고 계속 편집한다.

**검증 연결:** PV-02 → UI-02 input focus·paste·Undo → RG-02 stale/CAS/partial-save → IT-02 two-process recovery.


### FN-03 — 열 순서와 단위가 다른 시험 파일을 같은 관측량으로 연결

**사용자 / 완료 결과:** 시험 데이터를 받은 재료 연구자 · 숫자의 의미와 변환을 확인한 두 Data 관측을 Material에서 그대로 사용한다.

**추적:** R10, R12, R19, R20, R32, U§5, U§6 · 기존 T17, T18, T19 · UC01, UC10, UC17

**시작 조건:** 합성 tensile_A.csv는 time_s,force_N,extension_mm,temperature_C 순서; B는 extension_um,temperature_K,load_kN,time_ms 순서다. 서로 다른 시편, L0=50 mm, A0=20 mm², extensometer extension이라는 metadata를 제공한다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. DATA-MAP | A/B 원본 미리보기와 독립적인 열 선택, raw 단위→canonical 단위·scale·offset·변환 후 3행. | 이름 기반 채널을 지정한다. B extension ×0.001 mm, load ×1000 N, time ×0.001 s; 온도는 절대량 K 기준으로 변환한다. |
| 2. DATA-MAP | ‘단위 지정’과 ‘수치 변환’, source channel ID. 열명만 MPa로 바꾸는 오류 셀. | force/A0로 nominal stress P11, extension/L0로 engineering strain e11 파생 채널을 만든다. L0·A0가 없으면 해당 연산만 차단한다. |
| 3. DATA-EDIT | P11–e11 곡선과 원 row ID, 단위와 reference configuration, 관측 시간축. | 표 행·곡선 구간을 함께 선택해 원자료 값을 검토하고 Data 저장/관측 게시를 실행한다. |
| 4. MAT-PROTOCOL | Material 시험 목록의 A=train/B=holdout 제안, 정확 Data saved/import refs, P11와 axial stretch. | 관측으로 연결을 누르면 Material 안에 Data 편집 dock와 동일 Plan 관측표가 열린다. 별도 wizard 왕복은 없다. |
| 5. REOPEN-DATA | 원본301/241행·Data r4의 변환과 quality mask·저장 관측. | 같은 Data owner를 열어 표/매핑/교정 자료를 이어서 편집한다. Plan train/holdout는 덮어쓰지 않는다. |

**입력·단위·종속 조건:** 시간·하중·변위의 실제 열과 단위, 시편 길이/면적·측정 방식이 필요하다. e=ΔL/L0, λ1=1+e, P11=F/A0. Cauchy stress는 σ11=(λ1/J)P11이며 J 또는 현재 단면적을 실제 제공/검증한 변환이 있어야 한다. J=1은 명시 가정이고 default가 아니다. 로그 변형률 ln λ1은 λ1>0·해당 축의 변형 의미를 확인한다.

**저장·출력·재열기:** 원 CSV를 그대로 보존하고 Data owner가 mapping/quantity recipe/metadata·원 row ID·mask를 저장한다. 현재 numeric scale/offset을 재사용하며 기하 metadata·파생 연산은 typed recipe 확장이다. Material과 Plan은 변환 식을 복사 소유하지 않고 정확 관측 ref를 사용한다.

**오류·취소·복구:** 잘못된 열은 해당 선택 combobox에서 고친다. 구분자·소수점·encoding 오류는 원본 미리보기에서 고치며 원파일을 수정하지 않는다. 바뀐 단위가 수치 변환인지 metadata 정정인지 명시 선택한다. temperature offset은 ΔT에 다시 적용하지 않는다.

**현재 코드의 재사용:** DataDocuments, data.update/data.import, source_preview, file_table의 column/axis scale·offset·row_selection과 저장된 비교를 재사용한다. 기존 metadata는 test_id/specimen/protocol/temperature 문자열로 제한되므로 교정·기하 metadata는 추가다.

**추가·변경과 연결:** 원본/변환 후 이중 미리보기와 quantity-aware 변환 node, 다중 sheet 선택 모델을 추가한다. 하나의 Data owner에 이미 있는 파일 모델을 유지하고 여러 CSV를 sheet group로 보이되 데이터 ID를 합치지 않는다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. FN-01/02. 관측 연결에는 저장한 Data/import result가 필요하다. Material backend 설치는 가져오기·매핑의 선행이 아니다.

**사용자 완료 조건:** A/B의 같은 물리량이 같은 단위로 보이고 임의 셀의 원값→변환값을 손계산으로 추적한다. 열 재배치 후 채널 참조가 유지된다. 미확인 stress/strain measure로 fit을 실행하지 못한다.

**검증 연결:** PV-03 → UI-03 two-file mapping → RG-03 raw/scale/offset identity → NR-01 unit/quantity conversion; IT-03 retained reopen.


### FN-04 — 표–곡선으로 구간·mask·처리 이력을 편집

**사용자 / 완료 결과:** 시험·해석 시계열 분석자 · 원자료를 보존하면서 사용할 구간과 처리 방법을 선택하고 재사용 가능한 관측을 만든다.

**추적:** R10, R12, R20, R32, U§6 · 기존 T13, T17, T19 · UC01, UC05, UC10, UC17

**시작 조건:** Data에 원 row ID와 time 채널이 있고 raw와 processed가 분리된다. 단순 표시 축약은 계산값을 바꾸지 않는다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. DATA-EDIT | 왼쪽 raw/recipe tree, 중앙 표, 아래 곡선, 선택 40–110행과 time 4–11 s. | 곡선을 드래그하거나 Shift+행 선택, 숫자 구간 입력으로 같은 원 sample을 선택한다. 선택은 아직 mask가 아니다. |
| 2. DATA-INVALID | sample 82의 sensor dropout, mask 사유와 불연속 구간. | M 또는 우클릭 ‘품질 제외’로 source-quality mask를 저장한다. 행 삭제나 곡선 숨김으로 대신하지 않는다. |
| 3. DATA-EDIT | Filter/zero-shift/resample node의 입력·설정·출력 channel과 전후 곡선. | 실행 전 미리보기→Apply로 recipe 새 revision을 만든다. 원자료와 이전 처리 결과는 남는다. |
| 4. MAT-DIRTY | 관측 source mask와 Plan 연구 선택/holdout이 다른 열. | 연결된 관측을 Plan에 고정하고 fit 구간/weight만 Plan에서 바꾼다. |

**입력·단위·종속 조건:** 축 구간은 row 범위 또는 물리축 범위 중 하나로 저장하고 inclusive 경계를 명시한다. time 중복·비단조는 raw에 남긴다. 필터는 종류·차수·cutoff와 sampling 조건·끝단 guard를 가진다. 큰 데이터는 원행 paging+표시 downsampling으로 처리한다.

**저장·출력·재열기:** raw_quality_mask, operation_valid_mask, Plan inclusion/role, display_visibility는 별도 정의다. 최종 fit valid mask는 동결된 조건의 교집합이다. 제외 이유와 author/time·recipe revision을 보존한다. Undo로 mask/처리 변경을 되돌려도 raw hash는 같다.

**오류·취소·복구:** 지원하지 않는 irregular sampling 필터는 그 node를 차단하고 resample 정의로 이동한다. interpolation은 explicit method·max gap·범위·valid mask를 가진다. 연결된 결과가 갱신되어도 기존 Plan 관측을 자동 교체하지 않는다. 취소한 preview는 게시하지 않는다.

**현재 코드의 재사용:** file_table.validate_row_selection, Data mapping/retained input와 기존 curve comparison을 사용한다. 현재 strict reader의 실행 제한을 raw draft 저장 제한으로 확대하지 않는다.

**추가·변경과 연결:** QAbstractTableModel의 paging, shared selection model, plot SpanSelector와 원 sample resolver, 처리 recipe editor와 명시 transform service를 연결한다. 새 그래프 엔진이나 raw 데이터를 거대한 JSON draft에 넣지 않는다. 현재 quality_rows는 표시 metadata와 실행 제외가 분리되어 있고 Plan experiments에는 inclusion mask가 없다. Data 원 row ID→import sample index→quality/operation/Plan mask 교집합을 만드는 기존 owner schema/compiler 확장이 반드시 필요하다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. FN-03. 처리·선택은 Data 단독 가능하고 fit·Post 지원과 독립적이다.

**사용자 완료 조건:** masked gap이 선으로 연결되지 않고 raw/processed/Plan 포함 샘플 수가 일치한다. plot에서 선택한 한 점이 정확 원행으로 이동한다. 저장 후 mask·recipe·선택을 재열고 수정한다.

**검증 연결:** PV-04, UI-04 selection/keyboard/large table, RG-04 masks/recipe, NR-02 filter/interpolation reference, IT-03.


### FN-05 — 측정·교정·시험 조건을 예측과 맞추고 연구를 갱신

**사용자 / 완료 결과:** 시험 엔지니어·불량 원인 연구자 · 실제 측정이 예측의 어떤 양을 검증하는지 정의하고 새 자료로 모델 또는 판단을 갱신한다.

**추적:** R10, R11, R20, R32 · 기존 T17, T19, T22, T24 · UC09, UC10, UC12, UC14

**시작 조건:** 파일로 받은 시험 데이터·장비 교정표·게이지 위치가 있다. 없는 metadata는 UNKNOWN으로 남기며 장비 직접 연결은 필요 없다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. DATA-CALIBRATION | 시편·로트·장착·장비·교정 revision, voltage/count raw 채널과 변환식. | 보정계수·유효기간·단위·영점·uncertainty source를 연결하고 전후 값을 비교한다. |
| 2. POST-COMPARE | 측정 게이지의 두 위치·방향·게이지 길이, 예측 응답과 time alignment. | 동일 관측량을 선택한다. actuator displacement와 specimen strain을 같은 응답으로 묶지 않는다. |
| 3. NUM-OPTIMIZE | 식별 가능한 계수와 고정할 지그 강성/마찰, 새 시편의 train/holdout 구분. | 수치 inverse Plan을 만들어 실제 준비된 관측으로 평가한다. 재료와 지그 변수의 상관을 확인한다. |
| 4. STUDY-DECISION | 이전 모델·예측·새 관측, 지지/반박 근거와 미식별 항목. | 새 개정 채택 또는 보류, 구별력이 있는 후속 시험을 Study에 기록하고 저장한다. |

**입력·단위·종속 조건:** 보정 y=a·x+b의 계수 단위, offset이 적용되는 raw 범위, 센서 포화·영점·동기화·좌표/측정 방향·관측 시점이 필요하다. 불확실성이 제공되지 않으면 표준편차를 임의 생성하지 않는다. 전체 시험 metadata 중 사용하는 판단에 필요한 항목만 필수다.

**저장·출력·재열기:** Data가 raw·교정 recipe·장비/시편 metadata를, Post가 측정 비교를, Plan이 inverse/holdout을, 원 domain이 모델 개정을, Study가 판단을 소유한다. 교정 바뀜은 새 처리 revision이며 예전 데이터/판단을 소급 변경하지 않는다.

**오류·취소·복구:** 교정 유효범위 밖·포화·불명 orientation은 mask/불가 사유로 남긴다. 교정 파일이 없으면 raw는 열고 해당 물리량 변환만 막는다. 잘못된 시편 연결은 새 revision으로 수정하고 영향 받는 Plan에 stale notification을 보낸다.

**현재 코드의 재사용:** Data test_metadata와 retained comparison, study/research_context의 exact refs 및 domain adoption을 확장한다. 기존 교정·장비 프로토콜 전 범위 구현은 확인되지 않았다.

**추가·변경과 연결:** 교정 record의 typed unit/range·measurement definition, file-based test import와 predicted-observed comparison 연결. 장비 제어는 별도 FN-35로 남긴다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. FN-03/04/28/29. 파일 교정 경로에 장비 driver나 Expert provider를 요구하지 않는다.

**사용자 완료 조건:** 같은 raw sample에 적용한 교정·좌표/시간·게이지 정의와 모델 입력을 조회한다. 새 교정 또는 새 시험이 이전 결과를 덮어쓰지 않고 후속 연구에 연결된다.

**검증 연결:** PV-05, RG-05 calibration lineage, NR-03 independent unit/calibration check, IT-04 measurement→revision→decision.


### FN-06 — 재료 법칙과 시험 이력을 직접 평가

**사용자 / 완료 결과:** 구성모델 연구자 · 관측 없이도 재료점의 응답·상태·기본 법칙을 조사하고 유효 입력의 결과를 보존한다.

**추적:** R01, R17, R20, R29 · 기존 T18, T24 · UC01, UC02, UC03, UC07

**시작 조건:** 독립 Material 새 문서 또는 기존 law를 연다. Plan은 필요하지 않다. 기존 FELUPE와 등록 MFront law를 capability별로 표시한다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. MAT-EMPTY | 법칙 목록의 지원 operation·필요 runtime·응력척도·현재 상태. | 모델을 고르고 계수를 표에서 편집한다. 임의 law를 기존 backend 이름에 끼워 넣지 않는다. |
| 2. MAT-PROTOCOL | 축방향 제어 이력, 횡방향 자유/고정/전체 F 지정, 모델의 반환 stress measure. | time·strain/stretch/stress control과 온도·초기 상태를 설정한다. 자유 횡방향은 mixed-control 구현이 준비된 adapter만 실행한다. |
| 3. MAT-PROTOCOL | F11/F22/F33 및 determinant, 제어/응답 구별과 시간 단조성. | 현재 지원 ‘전체 F 지정’으로 직접 평가하거나 새 횡조건을 draft로 저장한다. 필수 불일치는 셀에서 수정한다. |
| 4. MAT-DIRTY | 직접 평가의 frozen input과 응력/에너지·state 곡선; 현재 draft와 다를 수 있다. | 원값과 tangent/state를 연다. ‘결과 보존’ 후 저장하면 새 프로세스에서 재계산 없이 읽는다. |

**입력·단위·종속 조건:** linear_elastic는 E>0, -1<ν<0.5; 현재 neo_hooke는 μ>0, λ_L+2μ/3>0이다. λ_L는 Lamé coefficient이고 axial stretch λ1과 다르다. 기존 stress_unit/time_unit은 labels이며 자동 변환하지 않는다. 전체 F(t)는 실제 3×3, det F>0, strictly increasing time. 초기 상태·stress control·온도는 law capability별 입력이다.

**저장·출력·재열기:** Material이 law/coefficients/protocol/initial state·integrator settings와 retained results를 소유한다. 직접 임시 평가의 모든 곡선을 강제로 영구 job로 만들지 않는다. 판단/채택에 사용하면 inputs·responses·diagnostics를 retain한다.

**오류·취소·복구:** 입력 중 오류는 저장 가능하지만 evaluate 차단. 횡방향 자유를 요청했는데 backend가 prescribed F만 지원하면 ‘지원 미완료: mixed-control’과 선택 복귀를 제공한다. 실패한 증분과 마지막 유효 state를 표시하고 뒤 sample을 이어 그리지 않는다.

**현재 코드의 재사용:** MaterialDocuments, material.update/material.evaluate, FelupeMaterialAdapter의 gradient/hessian, NativeMaterialWindow와 MFront 등록 경로를 재사용한다. 기존 default F22=F33=1을 일반 uniaxial tension으로 부르지 않는다.

**추가·변경과 연결:** protocol의 제어량·횡조건 UI와 이를 실제 F/stress-controlled integration으로 바꾸는 domain adapter 확장. 계수·상태·법칙별 입력 위젯은 typed descriptors로 제공하고 raw object editor를 주요 작업으로 쓰지 않는다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. FN-01/02. 현재 prescribed F 직접 평가는 Data/Plan 없이 가능하다. 새 transverse/stress-control은 해당 adapter/reference 검증만 필요하다.

**사용자 완료 조건:** 직접 평가와 fit이 별도 행동이며, 자유 인장과 횡구속 시험이 다른 결과를 낸다. 선택한 result의 응력척도/입력/상태를 재열기에서 유지한다.

**검증 연결:** PV-06, UI-06 protocol edit, RG-06 result identity, NR-04 prescribed vs traction-free, IT-03.


### FN-07 — 관측·잔차·holdout을 확인해 계수를 동정하고 채택

**사용자 / 완료 결과:** 재료 데이터 담당자 · 두 CSV에서 출발해 fit 후보의 장단점과 실패를 검토하고 충돌 없이 Material 새 개정으로 채택한다.

**추적:** R01, R17, R18, R20, R27, R32 · 기존 T17, T18, T19 · UC01, UC02, UC10, UC17

**시작 조건:** FN-03 관측 A/B가 보존되어 있고 FN-06의 시험 의미가 맞는다. 대표 합성 장면은 A 전체를 train, 다른 시편 B 전체를 holdout으로 둔다. 예측 법칙은 neo-Hooke, μ를 탐색하고 λ_L은 외부값으로 고정한다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. MAT-DIRTY | 시험 A/B 관측 refs·roles, Material current μ=0.85 MPa와 Plan lower=0.40/upper=1.40 MPa. | 같은 창에서 source Data dock, protocol, Plan 범위·mask·weight를 편집한다. Material 값과 Plan 범위는 별도 owner로 표시한다. |
| 2. MAT-PROTOCOL | P11/engineering strain/axial stretch·횡조건 검사가 맞는지, 학습과 holdout 표본 수. | 관측과 예측이 같은 measure/location/frame/time인지 검사한다. Cauchy↔Piola는 검증된 recipe가 없으면 실행을 막는다. |
| 3. MAT-FIT-RUNNING | method·seed·budget, frozen μ 범위/관측 revision, 현재 평가 수와 실제 실행 phase. | Fit을 실행한다. 편집을 계속하면 결과는 출발 snapshot에 붙는다. 전체 취소는 다음 후보 제출부터 중단한다. |
| 4. MAT-FIT-PARTIAL | 후보별 train objective·실패·상세보존 여부. best/확인 평가의 holdout만 실제 값, 다른 후보는 NOT_EVALUATED/NOT_RETAINED. | 행 선택으로 이미 보존된 원값/잔차만 연다. 없는 후보 곡선은 ‘선택 후보 상세·holdout 평가’를 명시 실행해 새 evaluation/ref/예산으로 얻는다. 행 선택은 계산하지 않는다. |
| 5. MAT-ADOPT-CONFLICT | 채택 후보 μ=0.862, fit 당시 Material r17, 현재 r18의 μ=0.90와 protocol 변경. | 기준/현재/후보 비교 후 새 분기를 만들거나 재검토한다. stale candidate를 현재 모델에 바로 덮어쓰지 않는다. |
| 6. RECOVERY-REOPEN | 채택 Material 새 revision, Plan·Data refs, 원 run/실패 후보·holdout 곡선. | Save related 후 새 프로세스에서 연다. 후보 선택이나 재열기로 숨은 fit을 수행하지 않는다. |
| 7. MAT-READY | 현재 미지원 입력은 blocked. 별도 미래 지원 상태는 PROPOSED / SIMULATED로 표시. | 미지원 Run으로 성공 상태를 만들지 않는다. 별도 미래 branch를 명시 선택해 지원이 구현된 뒤의 조작만 검토한다. |
| 8. MAT-ADOPT-DRAFT | 이전/현재 입력·draft·saved revision·정확한 결과와 해당 복구 상태. 같은 기능의 결과를 다른 예시로 대체하지 않는다. | 명시 Apply/Save/Cancel/재열기로 전이하며 frozen 결과는 원 입력에 남긴다. unsupported/invalid required 입력의 Run은 계속 차단한다. |
| 9. MAT-ADOPT-SAVED | 이전/현재 입력·draft·saved revision·정확한 결과와 해당 복구 상태. 같은 기능의 결과를 다른 예시로 대체하지 않는다. | 명시 Apply/Save/Cancel/재열기로 전이하며 frozen 결과는 원 입력에 남긴다. unsupported/invalid required 입력의 Run은 계속 차단한다. |
| 10. REOPEN-MAT-ADOPTED | 이전/현재 입력·draft·saved revision·정확한 결과와 해당 복구 상태. 같은 기능의 결과를 다른 예시로 대체하지 않는다. | 명시 Apply/Save/Cancel/재열기로 전이하며 frozen 결과는 원 입력에 남긴다. unsupported/invalid required 입력의 Run은 계속 차단한다. |
| 11. MAT-BRANCH-DRAFT | candidate c017/source17·현재 target18·새 문서ID M-branch-01. | 분기를 명시 생성한다. 원 Material·Plan은 바꾸지 않고 새 owner draft에 채택값을 반영한다. |
| 12. MAT-BRANCH-SAVED | M-branch-01 r1·derived_from r18/c017·원 target18불변. | 분기 저장 위치를 확인하고 새프로세스에서 동일 분기를 연다. |
| 13. REOPEN-MAT-BRANCH | 저장된 M-branch-01r1과 원 Material18·Plan8참조. | branch를 편집하되 원 Plan을 자동redirect하지 않는다. |

**입력·단위·종속 조건:** 관측 time는 명시 입력이며 strain 축을 time로 임의 변환하지 않는다. 목적함수는 동결된 fit 샘플에 대한 weighted residual; 자세한 식과 실패 비교는 부록 C2. weight>0, scale>0 및 scale의 단위가 response와 맞아야 한다. holdout은 optimizer에 들어가지 않는다. 상대 잔차에 0 분모가 있으면 미지정 또는 명시 scale을 사용한다. Plan starting value와 Material current value는 별도 열이다. 최신 Material 저장 후 ‘Plan 입력 갱신’에서 source ref·starting values·bounds·protocol diff를 확인하고 적용해야 한다. 취소하면 old Plan snapshot 유지; 새 current 값을 암묵 제출하지 않는다.

**저장·출력·재열기:** Data가 변환/품질 mask, Material이 protocol·coefficients, Plan이 fit 역할·선택·bounds/weights/budget·candidate 결과를 소유한다. 모두 exact saved/import refs로 묶는다. adoption receipt에 candidate/출발 및 도착 input revisions·hash·diff·새 revision을 보존한다.

**오류·취소·복구:** 일부 시험 실패한 후보는 incomplete이며 완전한 유효 후보보다 낮은 RMSE로 우선 정렬하지 않는다. 모든 후보 실패는 실패 원인별 grouping과 ‘입력 수정→새 run’이다. best candidate라도 holdout 실패면 완료·승인처럼 표시하지 않는다. λ_L 미식별은 숨기지 않고 외부 고정 근거를 표시한다.

**현재 코드의 재사용:** NumericalDocuments, fit_model, compare_curves/_aligned, candidate history와 domain/material adoption을 재사용한다. 현재 fit/holdout·weight·scale·frozen observations가 이미 있다. 새로운 optimizer를 만들지 않는다. 현 fit residual 후보행은 objective와 제한된 evaluation_refs 중심이며 full outputs cache는 유한하다. best_values의 holdout과 최종 curve만으로 임의 후보 곡선 보존을 주장하지 않는다.

**추가·변경과 연결:** Material 안의 동일 Plan 시험·변수표, residual/holdout 세부보기, candidate adoption 3-way preview, related-save와 partial success UX. 자유횡조건/quantity 변환은 FN-03/06의 완료된 기능을 연결한다. fit 결과 row에 상세/holdout의 NOT_RETAINED/NOT_EVALUATED를 추가하고 selected-candidate confirmation을 기존 evaluator의 새 evaluation으로 보존한다. 자동 상세 보존은 실행 전에 명시한 제한된 정책만 따른다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. FN-02/03/04/06. fit 자체의 데이터/평가기 경로를 먼저 연결하며 Contact/PDE/Expert는 선행이 아니다.

**사용자 완료 조건:** 서로 다른 두 CSV 매핑→mask→역할 설정→fit→부분/실패 후보→충돌→새 분기 채택→save→cold reopen을 중간 창 왕복 없이 마친다. 확인되지 않은 계수를 식별 성공으로 쓰지 않는다.

**검증 연결:** PV-07, UI-07 full Material script, RG-07 frozen role/late result/adoption, NR-05 identifiable synthetic fit, IT-03.


### FN-08 — 구성 적분·상태·접선을 연구하고 사용자 법칙을 등록

**사용자 / 완료 결과:** 구성모델·솔버 알고리즘 연구자 · 증분 크기·내부 상태·consistent/continuum tangent 차이를 독립 기준으로 검토한다.

**추적:** R01, R17, R29, R31, R39 · 기존 T18, T24, T25 · UC02, UC03, UC07, UC15

**시작 조건:** Material에서 지원 law 또는 명시 등록할 MFront 구현을 선택한다. 실제 코드/빌드·interface 버전이 있는 법칙만 실행 후보로 등록한다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. MAT-CONSTITUTIVE | law source/build/interface, stress/strain measure, state 변수, integration history. | 인장·압축·전단·제하·반복 등 protocol을 선택하고 초기 state와 증분 순서를 정의한다. |
| 2. MAT-CONSTITUTIVE | 선택 증분의 trial/committed state, local residual·substep·return mapping 진단. | 실패 증분을 확대하고 step size만 바꾼 새 evaluation을 만든다. 이전 state를 수동 덮어쓰지 않는다. |
| 3. MAT-CONSTITUTIVE | 반환 tangent와 기준 directional derivative, perturbation scale별 오차 곡선. | 정확한 stress/strain pair·tensor index·frame을 고른 뒤 FD/complex-step 가능한 경우만 독립 검사를 실행한다. |
| 4. REPORT-REVIEW | 양호/불량 tangent 비교와 원 law·빌드·settings·reference. | 검토 결과를 보존하고 FE material 할당에는 별도의 solver interface 지원 검사를 요청한다. |
| 5. REOPEN-CONSTITUTIVE | prescribed F 연구 정의·합성 reference·FD미실행 상태. | 같은 Material 연구로 열어 증분/접선을 이어서 검토한다. retained라는 이유로 evaluator실행을 꾸미지 않는다. |

**입력·단위·종속 조건:** 소변형/유한변형, 객관률, 응력·변형 measure, 내부 변수 초기값, tangent ∂P/∂F 또는 선택 pair를 명시한다. consistent tangent는 구현된 discrete update를 미분한 값; continuum tangent와 서로 이름만 바꿔 비교하지 않는다. 비매끄러운 yield 전환/손상 지점은 one-sided·active set 조건을 기록한다.

**저장·출력·재열기:** 법칙 source·compile log·binary hash·TFEL/interface version, exact input, committed state·probe 값·실패 지점을 보존한다. 빌드 권한과 평가 권한은 별개다. arbitrary code는 typed parameter 편집만으로 실행되지 않는다.

**오류·취소·복구:** compile 실패·unsupported interface·nonpositive J·local solver failure·nondifferentiable 지점을 구분한다. tangent 불일치가 나도 응력 이력과 실패 수치는 보존한다. 임계값을 바꾸지 않고 기준/step refinement를 별도 새 비교로 기록한다.

**현재 코드의 재사용:** 등록 MFront domain/adapters와 FELUPE hessian 결과를 재사용한다. 기존 특정 SVK/Maxwell/J2·DP family의 범위를 임의 구성식/FE interface 전체로 확대하지 않는다.

**추가·변경과 연결:** Constitutive inspector, state/step comparison, compatible tangent-pair validator, explicit compile/register workflow. Core는 source/record와 gate만; constitutive math와 FD 정책은 Domain, native MFront syntax는 Adapter다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. FN-06. law-specific runtime 및 독립 reference가 해당 실행만 제약한다. 일반 Material UI·Data 기능의 gate가 아니다.

**사용자 완료 조건:** 같은 discrete update의 초기 상태를 복원하며 perturbation 시험을 수행하고, 잘못된 tangent가 실패로 남는다. cyclic history에서 반복 횟수가 다른 초기화를 섞지 않는다.

**검증 연결:** PV-08, UI-08 state inspection, NR-06 tangent/local integration independent tests, RG-08 input-state isolation.


### FN-09 — 검증된 재료 모델을 해석용 할당과 solver 카드로 전달

**사용자 / 완료 결과:** 재료 담당자와 FE 모델 작성자 · 채택 계수의 물리 의미·단위·interface를 유지하며 특정 해석의 재료로 사용한다.

**추적:** R17, R19, R26, R29, R30 · 기존 T08, T18, T24, T25 · UC02, UC05, UC07, UC09

**시작 조건:** 저장 Material law/계수 revision과 대상 Simulation/native Analysis를 선택한다. fit 점수가 좋다는 이유로 카드 변환을 허용하지 않는다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. MAT-FE-TRANSFER | source law·measure·state·단위와 target solver/version·law·element family 지원표. | ‘해석에 할당’에서 지원되는 변환을 고른다. adapter가 없으면 draft mapping만 저장한다. |
| 2. MAT-FE-TRANSFER | 계수 mapping 표와 단위 변환, 누락/추가 필수값·온도/rate 범위. | 공급되지 않은 값은 직접 근거와 함께 입력한다. 임의 default strength/failure 값은 채우지 않는다. |
| 3. PRE-FEM | 할당 solid/shell/beam region·orientation·두께와 Material ref. | native 선택으로 적용 대상을 고르고 중복/미할당을 검사한다. |
| 4. SIM-IMPLICIT | 지원 카드 미리보기와 provenance, 필요한 material-point 또는 single-element 검증. | 입력 생성 후 해당 adapter gate를 통과한 snapshot만 실행한다. export된 파일과 원 Material을 저장한다. |
| 5. REOPEN-FE-ASSIGNMENT | 정확 lawr19→Bracketr12/Base assignmentdraft와 미검증card. | native target Analysis를 다시 열어 호환성진단을 수정한다. draft저장은 exportadmission을 바꾸지 않는다. |

**입력·단위·종속 조건:** solver별 stress/strain measure·density·elastic/plastic/visco/hyper/failure parameters, anisotropy orientation, temperature/rate, section thickness/units가 필요하다. nominal plastic strain을 total true strain처럼 해석하지 않는다. 해당 law의 admissible range를 검사한다.

**저장·출력·재열기:** Material source revision과 target material assignment의 변환 receipt를 저장한다. target의 physics 값 소유는 Simulation/Pre이고 Material 원본을 바꾸지 않는다. 이후 Material 최신 revision은 ‘새 개정 있음’으로 알리고 자동 적용하지 않는다.

**오류·취소·복구:** 미지원 law/element/finite-strain 조합은 문제 셀과 대안을 보여준다. 단위를 정정하면 새 mapping revision이며 과거 deck를 대체하지 않는다. 부분 대상 할당을 전체 성공으로 표시하지 않는다.

**현재 코드의 재사용:** native FEM assignments, Simulation owner와 registered MFront/FELUPE 지원 경로를 확장한다. 현재 source 조사만으로 arbitrary material-to-solver export를 확인한 것은 아니다.

**추가·변경과 연결:** Material assignment transfer dialog/dock, per-solver capability descriptors, explicit quantity converter와 reference tests. Native 재료 Tasks를 중복 구현하지 않고 검증·provenance 연결을 추가한다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. FN-06/08/12 및 선택 solver adapter. Data 또는 Numerical은 외부 고정 물성 할당의 선행이 아니다.

**사용자 완료 조건:** source coefficient와 solver deck의 실제 값/단위·할당 영역을 추적하고 single-element 기준이 적용된다. 변환 미지원이면 저장 가능한 초안과 명시 export 차단을 제공한다.

**검증 연결:** PV-09, UI-09 assignment, RG-09 revision mapping, NR-07 solver-law/interface validation.


### FN-10 — 자기 CAD의 치수·피처를 편집하고 연구 변수로 등록

**사용자 / 완료 결과:** 기구·지그 설계 엔지니어 · 기존 native 이력을 유지하며 유효한 설계 변경과 탐색 가능한 변수 대상을 만든다.

**추적:** R04, R06, R07, R08, R25, R26 · 기존 T05, T06, T10 · UC09, UC05

**시작 조건:** 자기 FCStd 또는 STEP/IGES를 FreeCAD native로 연다. 가져온 BRep에 원 스케치 이력이 없으면 그대로 표시한다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. PRE-DESIGN | 활성 Body/Part·Sketch·Feature 이력과 큰 3D, 선택한 named constraint. | native Sketcher/PartDesign Tasks에서 치수 또는 피처를 편집·재계산한다. 모델 트리 선택과 3D 강조가 일치한다. |
| 2. PRE-DESIGN | 변경 전후 형상, invalid feature 또는 이전 정상 형상 표시. | Lab 검사에서 실패 feature로 이동하거나 native Undo로 복구한다. invalid draft 저장은 허용한다. |
| 3. PRE-DESIGN | ‘연구 변수 등록’의 실제 object/path·unit·type·dependency, 현재값. | 선택 속성만 등록한다. display name과 stable research ID, native target을 분리한다. |
| 4. NUM-DOE | 등록 변수의 model bounds/종속성, 이번 Plan의 free·search bounds. | Plan 범위를 따로 정한다. 실제 효과 검사는 명시한 perturbation과 관측 범위를 기록한다. |

**입력·단위·종속 조건:** 치수·속성은 native 지원 단위와 타입을 따른다. 등록 경로에는 document/object/instance/property·geometry revision·native type을 포함한다. expression 종속 변수는 직접 자유변수로 바꾸지 못한다. 해당하지 않는 기본값·bound 필드를 의무화하지 않는다.

**저장·출력·재열기:** managed .caepre는 editable FCStd graph와 refs를 보존한다. 연구 변수 registry는 exact target과 native edit 후 refresh 결과를 저장한다. 똑같은 face index 또는 constraint index만으로 항구적 semantic identity를 만들지 않는다.

**오류·취소·복구:** 선택 대상 삭제/constraint reorder/index drift는 reference refresh·수리로 안내한다. 효과가 작았던 변수는 해당 관측에서 무반응이라는 기록이며 전역 삭제하지 않는다. native task가 열린 동안 충돌 command는 BUSY_EDIT이다.

**현재 코드의 재사용:** Pre bridge/parameters/parameter_panel/native_controls 및 upstream discovery를 재사용한다. 기존 생성 fixture에만 맞춘 UI로 일반 설계 요구를 축소하지 않는다.

**추가·변경과 연결:** native 선택에서 실제 연구 등록·refresh로 들어가는 context command, inactive/suppressed/derived 표시, 두 번째 사용자 모델 수용 경로를 보완한다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. FN-01/02, FreeCAD. Numerical이 없어도 CAD 편집·저장이 가능하다.

**사용자 완료 조건:** fixture 이외 모델 두 개에서 치수 변경→재계산→변수 등록→재열기 재편집을 완료한다. invalid CAD는 해당 export/run을 막는다.

**검증 연결:** UI-10 native CAD; RG-10 target identity; NR-08 geometry effect; IT-05 .caepre reopen.


### FN-11 — 조립·관절·운동 경로를 검토하고 설계 자세를 보호

**사용자 / 완료 결과:** 지그·기구 설계 엔지니어 · 조립 운동을 확인한 뒤 preview pose가 설계/FEM/저장에 섞이지 않도록 한다.

**추적:** R01, R07, R11, R12, R26, U§6 · 기존 T07, T10 · UC09

**시작 조건:** FreeCAD Assembly에서 native parts/links와 지원 joint를 선택한다. 운동학 작업에 해석 solver는 필요 없다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. PRE-MOTION | 부품 정의와 배치 Link, joint axis/limits, 설계 P0와 preview frame. | native Assembly로 부품·고정·관절을 만들고 시간/drive expression을 설정한다. |
| 2. PRE-MOTION | native 계산 phase·frame 개수와 supports_cancel, trace point의 로컬/세계 좌표. | 운동 계산 뒤 slider/재생으로 frame을 본다. trace point 선택→경로·time 표를 연결한다. |
| 3. PRE-MOTION | 일시정지·설계 자세 복원·현재 자세 적용이라는 세 동작. | 일시정지는 frame 유지, Stop/Cancel은 P0 복원. ‘현재 자세 적용’만 지원 native 정의의 새 설계 transaction이다. |
| 4. PRE-RESTORE-FAILED | 부품별 P0/실제 placement 차이와 출발/current generation. | 복원 미확인이면 저장/FEM 전환/export를 차단한다. 지금 상태 읽기→사용자 편집 대조→지원 복원 또는 새 분기를 선택한다. |
| 5. PRE-FEM | 설계 자세 복원 확인과 exact CAD revision. | FEM으로 전환한다. 적용한 P1에는 과거 preview의 P0 restore를 다시 보내지 않는다. |

**입력·단위·종속 조건:** native joint 종류·axis·offset·limits와 drive expression parser는 pinned FreeCAD/bridge 지원을 따른다. 현재 motion code의 2,001 frames·8 traces 등 bounds는 실제 지원 범위 표시이며 전체 제품 기능 수의 상한이 아니다. displacement frame은 접촉력/응력이 아니다.

**저장·출력·재열기:** design pose·preview session+start generation·frames/path·selected view frame을 구분한다. 새 프로세스에서는 설계 pose로 시작하고 보존 경로는 재계산 없이 읽는다. 일반 Save는 restore-first를 검증한다.

**오류·취소·복구:** native generation/path sampling이 동기·중단 불가인 단계는 cancel disabled+실제 상태로 둔다. 재생 취소와 native 계산 중단을 구별한다. restore 적용 전 generation이 달라지면 옛 restore로 새 사용자 편집을 덮어쓰지 않는다.

**현재 코드의 재사용:** motion.py의 Motion.OPERATIONS, motion_panel.py, existing native Assembly·preview restore·adopt-pose·trace를 재사용한다. 새로운 motion solver를 만들지 않는다.

**추가·변경과 연결:** 설계/preview 상태 띠·복원 실패 diff·save/FEM gate 연결, visible Windows native 반복 확인과 장시간 phase UX를 보완한다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. FN-10 및 native Assembly. contact/implicit 해석 완료는 운동학 편집의 선행이 아니다.

**사용자 완료 조건:** P0→P1 preview→pause/stop/save→새 FreeCAD P0가 확인된다. 명시 pose 적용 시에만 새 generation의 P1을 저장하고 Undo도 증가 generation으로 기록한다.

**검증 연결:** PV-11, UI-11 native motion/focus, RG-11 stale restore, IT-05 pose save/FEM isolation.


### FN-12 — 해석용 표현·영역·재료·하중·조건을 모델에 배치

**사용자 / 완료 결과:** FE 모델 작성자 · 설계 형상에서 실제 해석 대상을 골라 의미와 단위가 맞는 입력을 구성한다.

**추적:** R01, R08, R19, R26, R29, R30 · 기존 T08, T10, T11 · UC05, UC06, UC07, UC09

**시작 조건:** native FEM Analysis 또는 외부 mesh/deck 기반 Simulation으로 시작한다. CAD 없는 external model에는 가짜 CAD parent를 만들지 않는다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. PRE-FEM | 설계 CAD와 analysis representation, 포함/제외·공유/접촉/tie 경계. | 다부품을 무조건 fuse하지 않고 body별 해석 참여와 차원 solid/shell/beam을 정한다. |
| 2. PRE-FEM | body/face/edge/point selection filter, set 이름·개수·면적·revision. | Ctrl/Shift 또는 Add/Remove 목록으로 region을 만든다. 화살표와 대상 목록을 함께 확인한다. |
| 3. PRE-FEM | 재료/section·orientation·load/BC와 active Analysis. | native Tasks에서 힘/압력/변위/온도/초기조건을 편집한다. total force와 pressure를 다른 quantity로 입력한다. |
| 4. SIM-IMPLICIT | 선택 solver의 입력 지원표, 할당 누락·중복·unsupported 조건. | preflight에서 문제 행으로 이동해 수정하고 유효 snapshot을 Runner로 보낸다. |

**입력·단위·종속 조건:** 좌표계·방향·단위·step·진폭/time curve와 region references가 명시되어야 한다. beam/shell의 thickness/section/orientation, composite ply/layer·local coordinate는 실제 adapter 지원별로 저장한다. native assembly constraint는 FEM BC로 자동 변환하지 않는다.

**저장·출력·재열기:** native Model/Tasks/FEM objects, Analysis revision과 representation-to-design 관계를 .caepre에 보존한다. 외부 deck는 raw files+includes+adapter descriptor를 Simulation에 보관하고 native syntax를 Core에 펼치지 않는다.

**오류·취소·복구:** 형상 변경 후 old mesh·region ambiguity·normal flip·새 미할당 body는 영향 목록에 남긴다. geometry 번호 일치만으로 region을 복구하지 않는다. 지원하지 않는 required 조건은 실행/export를 막고 draft는 저장한다.

**현재 코드의 재사용:** fem_edit/fem_panel/mesh_binding, SimulationDocuments와 frozen native path를 재사용한다. 현재 freeze admission은 주로 단일 solid C3D10/선형 native 경로로 bounded이며 광범위 FE를 입증하지 않는다.

**추가·변경과 연결:** region/assignment 화면의 선택과 capability 진단·geometry repair를 연결한다. pressure/displacement/composite/connector/preload 등은 각 domain/adapter 지원 과제로 분해한다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. FN-10/13/33. 외부 model 진입에는 FreeCAD가 필수는 아니다. 지원 없는 solver 메뉴는 disabled 이유를 갖는다.

**사용자 완료 조건:** 실제 할당 대상과 입력 deck의 node/element/face set이 맞으며 누락 조건이 조용히 제거되지 않는다. 불유효 모델 저장 후 재열어 고칠 수 있다.

**검증 연결:** UI-12 selection/Tasks, RG-12 mapping/export rejection, NR-09 load/unit checks, IT-06 prepare→run.


### FN-13 — 메시를 생성·개선하고 품질 결함의 실제 요소로 이동

**사용자 / 완료 결과:** 전처리 엔지니어 · 국부 크기를 바꿔 실제 메시 품질과 재현 가능한 입력을 개선한다.

**추적:** R08, R09, R26, R29, R34 · 기존 T09, T10, T11 · UC05, UC08, UC09

**시작 조건:** 유효 analysis representation과 mesher capability가 있고 이전 mesh가 있으면 비교 대상으로 보존한다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. PRE-MESH-QUALITY | native Gmsh Tasks의 전체/국부 크기와 target region, 현재 mesh geometry revision. | global size와 selected-face local size를 정하고 생성한다. total 미지정이면 spinner/phase만 표시한다. |
| 2. PRE-MESH-QUALITY | 새 mesh의 요소 수·유형, quality 지표 분포·실제 sampled/full 범위. | 불량 구간 또는 요소 행을 선택하면 3D에서 해당 element를 강조·격리·확대한다. |
| 3. PRE-MESH-QUALITY | 국부 mesh 설정 및 주변 geometry, before/after 품질 비교. | refinement를 수정하고 부모 mesh에서 regenerate한다. 설정 변경만으로 current mesh라 표시하지 않는다. |
| 4. PRE-FEM | 새 mesh 적용 후 region/condition 재연결 상태. | 검사된 mesh를 해당 Analysis에 적용하고 기존 mesh·quality 기록을 남긴다. |
| 5. COMMAND-MESH | command_id mesh-006·geometryr12/startg41·취소요청·NOT_APPLIED와 보존meshr6. | 같은 command_status/cancel을 사용한다. 취소접수와 실제terminal/applygeneration을 구별하고 job_id로 조회하지 않는다. |

**입력·단위·종속 조건:** element family/order·length unit·min/max/local size·growth/quality threshold는 mesher/element별 의미로 제공한다. Jacobian 샘플 검사를 전체 영역의 양수 보증으로 확대하지 않는다. 기하 공차와 mesh 크기·품질 임계값은 별개다.

**저장·출력·재열기:** mesh hash/element connectivity/geometry revision/settings·quality definition/version·bad element IDs와 원 로그를 저장한다. 실패 생성은 기존 mesh를 대체하지 않는다.

**오류·취소·복구:** mesher 실패·취소·stale output은 새 결과를 보존하되 native 적용 안 함을 표시한다. native task에서 취소가 불가하면 지원 없음으로 둔다. 생성 동안 CAD가 바뀌면 old geometry result를 자동 채택하지 않는다.

**현재 코드의 재사용:** 기존 native Gmsh/MeshRegion, mesh_binding와 upstream native structural/assembly mesh workers를 재사용한다.

**추가·변경과 연결:** quality histogram·element table·selection linking, incremental status/command monitor와 generation-checked apply를 보완한다. 별도 mesher/scheduler를 만들지 않는다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. FN-12와 실제 mesher. 해당 요소의 quality 검증은 이 기능에만 연결한다.

**사용자 완료 조건:** 선택 불량 요소가 실제 mesh ID와 일치하고 local refinement 후 quality/개수가 변한다. 실패·취소·stale 결과에서도 이전 실행 가능 mesh가 남는다.

**검증 연결:** UI-13, RG-13 mesh result apply, NR-10 quality metric independent definition, IT-06.


### FN-14 — 사용자 면 집합의 접촉을 정의·해석·복구

**사용자 / 완료 결과:** 비선형 접촉 해석 엔지니어 · 자기 모델의 접촉조건부터 압력·힘·gap·slip 결과와 형상 변경 후 재연결까지 끝낸다.

**추적:** R01, R08, R19, R26, R29, R30 · 기존 T08, T10, T24, T25 · UC05, UC07, UC08, UC09

**시작 조건:** 두 독립 body의 named face sets를 선택한다. bounded benchmark가 있는 것은 일반 사용자 contact exporter 지원과 다르다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. PRE-CONTACT | A pad-bottom 4 faces(320 mm²), B base-top 2 faces(336 mm²), normal arrows·closest gap. | face filter/Ctrl 또는 목록 Add/Remove로 두 set을 지정한다. 목록 행 선택↔3D 강조, A/B 교체는 별도 명령이다. |
| 2. PRE-CONTACT | normal law·friction law·μ=0.15·initial clearance=0.20 mm, orientation와 detection 영역. | law를 고르면 필수 접선/normal/penalty 옵션만 펼친다. gap 값은 typed 단위와 실제 형상 진단을 나란히 표시한다. |
| 3. PRE-CONTACT-UNSUPPORTED | 선택 solver/version·surface formulation·element pairing의 지원, 미지원 cohesive 또는 large-sliding 항목. | preflight 오류 행에서 조건을 고치거나 지원 adapter를 선택한다. law를 자동 다른 법칙으로 바꾸지 않는다. |
| 4. RUN-ACTIVE | frozen contact sets와 step, iteration/cutback·contact search 로그. | 실행·취소·실패를 Runner에서 추적한다. 실패는 source contact/normal/step 설정으로 돌아가 새 run을 만든다. |
| 5. POST-CONTACT | actual t=0.040 s·contact pressure/normal force/gap/penetration/slip·status, 양 surface 관계. | pressure cell 선택→같은 contact point/face의 time curve·원값을 읽는다. force sum과 pressure integral의 의미/위치를 확인한다. |
| 6. PRE-CONTACT-REBIND | geometry split 후 old A4→new A7 candidate, 면적·centroid·normal 비교, 1 face normal flip. | old set translucent overlay에서 후보를 검토하고 new faces를 직접 골라 preview한다. Rebind Apply는 새 contact revision; Cancel은 원 참조를 unresolved로 보존한다. |
| 7. REOPEN-CONTACT | 이 도구의 정확한 saved owner·입력·결과·누락 branch, 새 session. | 같은 도구 편집/보존 결과/영향받은 참조 복구 중 선택한다. 자동 실행하지 않는다. |
| 8. PRE-CONTACT-READY | 현재 미지원 입력은 blocked. 별도 미래 지원 상태는 PROPOSED / SIMULATED로 표시. | 미지원 Run으로 성공 상태를 만들지 않는다. 별도 미래 branch를 명시 선택해 지원이 구현된 뒤의 조작만 검토한다. |
| 9. RUN-CONTACT | 선택 기능의 job/attempt/frozen input/result, cancel scope와 실제 종료 관측. | 정확한 source editor/result를 연다. 취소 요청은 새 제출을 멈추며 terminal이 확인될 때까지 현재 실행을 보존한다. |
| 10. RUN-CANCEL-CONTACT | 선택 기능의 job/attempt/frozen input/result, cancel scope와 실제 종료 관측. | 정확한 source editor/result를 연다. 취소 요청은 새 제출을 멈추며 terminal이 확인될 때까지 현재 실행을 보존한다. |
| 11. PRE-CONTACT-CANCELLED | 이전/현재 입력·draft·saved revision·정확한 결과와 해당 복구 상태. 같은 기능의 결과를 다른 예시로 대체하지 않는다. | 명시 Apply/Save/Cancel/재열기로 전이하며 frozen 결과는 원 입력에 남긴다. unsupported/invalid required 입력의 Run은 계속 차단한다. |
| 12. PRE-CONTACT-REBOUND | 이전/현재 입력·draft·saved revision·정확한 결과와 해당 복구 상태. 같은 기능의 결과를 다른 예시로 대체하지 않는다. | 명시 Apply/Save/Cancel/재열기로 전이하며 frozen 결과는 원 입력에 남긴다. unsupported/invalid required 입력의 Run은 계속 차단한다. |
| 13. REOPEN-CONTACT-CANCELLED | 이전/현재 입력·draft·saved revision·정확한 결과와 해당 복구 상태. 같은 기능의 결과를 다른 예시로 대체하지 않는다. | 명시 Apply/Save/Cancel/재열기로 전이하며 frozen 결과는 원 입력에 남긴다. unsupported/invalid required 입력의 Run은 계속 차단한다. |
| 14. REOPEN-CONTACT-R13 | 이전/현재 입력·draft·saved revision·정확한 결과와 해당 복구 상태. 같은 기능의 결과를 다른 예시로 대체하지 않는다. | 명시 Apply/Save/Cancel/재열기로 전이하며 frozen 결과는 원 입력에 남긴다. unsupported/invalid required 입력의 Run은 계속 차단한다. |

**입력·단위·종속 조건:** normal law(open/compression/tie/cohesive는 별개), friction law와 μ≥0, penalty stiffness 단위·effective thickness·initial gap/overclosure policy·normal convention·large/small sliding·step activation이 필요하다. frictionless 선택 시 μ는 비활성 N/A이며 과거값은 retained draft로 남는다. gap>0=open, penetration>0은 선택 solver의 signed gap에서 도출하는 recipe와 함께 표시한다.

**저장·출력·재열기:** contact ID·A/B region refs·CAD/mesh revision·law/μ/gap/normal policy·mapping·support/preflight receipt·results/time/association을 보존한다. 원 definition과 과거 결과는 geometry split 뒤에도 열 수 있다. 재연결 취소가 옛 정상 입력을 새 형상에서 유효하게 만들지는 않는다.

**오류·취소·복구:** 누락 set/동일 body self-contact 미지원/뒤집힌 법선/초기 과도 침투/미지원 element pair는 해당 대상에서 고친다. 결과 채널이 없으면 ‘출력 요청 없음/reader 미지원/미발생’을 구별하고 0을 쓰지 않는다. contact off 조건의 결과를 frictionless contact 결과로 대신하지 않는다.

**현재 코드의 재사용:** native selection/region·fem_edit·reference repair·Runner·Post measurement를 재사용한다. 현 freeze_analysis의 ‘no contact’ 제한은 유지한다. broad user contact exporter와 contact field semantics는 추가 작업이다.

**추가·변경과 연결:** Contact editor는 selected object의 Tasks/dock로 구현한다. law-specific native exporter, capability matrix, preflight, contact-specific response reader와 rebind transaction을 연결한다. full user contact를 위해 사용자 모델 2개와 split/normal flip 검증이 필요하다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. FN-12/13/15 또는 FN-16, FN-25/27. UI 초안·저장은 solver 미설치 상태에서도 가능하다. backend의 contact 실행 지원이 이 실행의 gate다.

**사용자 완료 조건:** 자기 face sets→law/μ/gap/normal→unsupported 수정→run→pressure/force/gap/penetration/slip/time→save→split/normal flip→rebind cancel/적용→재열기를 완료한다. benchmark 하나의 PASS는 이 수용을 대체하지 않는다.

**검증 연결:** PV-14, UI-14 selection/rebind; RG-14 exact-set/cancel; NR-11 contact force/gap/friction reference; IT-07 complete contact journey.


### FN-15 — 비선형 implicit 해석의 하중 단계·수렴·응답을 다룸

**사용자 / 완료 결과:** 구조해석 엔지니어 · 재료/기하 비선형·접촉을 포함한 static 또는 지원 implicit dynamics를 준비하고 실패 원인을 추적한다.

**추적:** R01, R14, R26, R29 · 기존 T11, T24, T25 · UC02, UC06, UC08, UC09

**시작 조건:** native FE 또는 external mesh/deck Simulation에서 물리 step을 정의한다. Code_Aster 주력 후보·CalculiX 보조의 실제 capability를 구분한다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. SIM-IMPLICIT | model/mesh/material refs, nonlinear geometry·law·contact, step loading. | NLGEOM·load steps·initial state·time control을 source domain에서 편집한다. |
| 2. SIM-IMPLICIT | increment min/initial/max, nonlinear tolerance·line search/solver·output frequency. | 물리적 의미와 단위가 있는 설정을 고르고 preflight한다. Runner 자원 설정과 섞지 않는다. |
| 3. RUN-ACTIVE | physical time/load factor·iteration·residual/cutbacks, wall time 별도. | 현재 수렴 곡선과 진단을 읽는다. 수치 정책 수정은 새 입력/run이며 같은 attempt retry가 아니다. |
| 4. POST-MEASURE | 하중–변위·반력·소성/접촉/에너지와 mesh/step-dependent response. | 원 sample·선택 요소와 응답 curve를 비교하고 retained result를 저장한다. |
| 5. REOPEN-SIMULATION | 이 도구의 정확한 saved owner·입력·결과·누락 branch, 새 session. | 같은 도구 편집/보존 결과/영향받은 참조 복구 중 선택한다. 자동 실행하지 않는다. |

**입력·단위·종속 조건:** analysis static/implicit dynamic, finite strain flag, history-dependent material/initial state·BC/load sequences, solver tolerances·stabilization과 그 에너지, output requests. 시간 단위와 pseudo-time/load factor를 구별한다.

**저장·출력·재열기:** domain input·deck/includes·solver build·mesh/material refs·step settings·attempt logs·partial fields를 exact result로 보존한다. 최종 frame만 저장해서 수렴 과정을 잃지 않는다.

**오류·취소·복구:** divergence/negative Jacobian/contact search failure·memory/launcher failure를 구별해 source 객체로 이동한다. last converged increment와 rejected increments를 표시한다. parameter relaxation이나 tolerance 변경은 명시 새 설정이며 원 기준을 변경하지 않는다.

**현재 코드의 재사용:** SimulationDocuments와 existing Code_Aster/CalculiX bounded adapters·JobManager·Post reader를 재사용한다. native 단일 solid 선형 freeze는 이 범위의 완성 증거가 아니다.

**추가·변경과 연결:** 지원 model/step descriptors, nonlinear settings editor, convergence diagnostics, physics-specific result requests와 adapter 확장. 여러 solver를 한 숫자폼으로 같게 보이지 않게 한다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. FN-09/12/13/14 관련 항목, FN-25/27. 각 law/analysis별 수치 기준은 해당 지원 확대 때 수행한다.

**사용자 완료 조건:** 선형 limit·기하비선형·소성·접촉 사례를 각각 설정·실행·실패수정·저장하고 비교한다. ‘프로세스 정상 종료’와 수렴·유효·release를 따로 읽는다.

**검증 연결:** PV-15, UI-15 step/convergence; RG-15 snapshot/retry; NR-12 linear/nonlinear/implicit dynamic references; IT-06.


### FN-16 — explicit 충격·낙하의 초기조건·접촉·에너지를 연구

**사용자 / 완료 결과:** 가전 포장·낙하해석 엔지니어 · 조립 모델의 낙하 조건과 출력 요청을 준비해 실제 충격 결과와 실패를 비교한다.

**추적:** R01, R15, R30 · 기존 T24, T25 · UC05

**시작 조건:** 지원 external/native FE 모델에서 explicit analysis를 만든다. OpenRadioss 계열의 실제 설치 binary/repository identity를 선택하며 이름 변경·후속 배포가 확인되지 않으면 자동 대체하지 않는다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. SIM-EXPLICIT | body/rigid/material/contact·floor normal, COM·orientation·drop height/velocity. | height+gravity로 계산한 이상화 speed 또는 측정된 pre-impact v/ω 중 입력 모드를 명시한다. 두 모드를 몰래 중복 적용하지 않는다. |
| 2. SIM-EXPLICIT | end time·time step/CFL·mass scaling·contact/failure output request. | 단위계와 control을 정하고 미지원 card/connector/composite를 preflight한다. |
| 3. RUN-ACTIVE | physical time·minimum timestep·added mass·kinetic/internal/contact/hourglass energy. | actual solver logs를 추적하고 중단/불안정 원인을 확인한다. |
| 4. POST-CONTACT | contact sequence·force/acceleration/time·deformation·failure field. | 정확 frame과 event/peak 정의로 응답을 비교한다. acceleration filter는 별도 recipe로 표시한다. |
| 5. REPORT-REVIEW | 원 input·energy balance·mesh/time-step sensitivity·물리 시험 비교 여부. | 결과와 한계를 저장하고 physical validation 미제공이면 UNKNOWN을 남긴다. |
| 6. REOPEN-SIMULATION | 이 도구의 정확한 saved owner·입력·결과·누락 branch, 새 session. | 같은 도구 편집/보존 결과/영향받은 참조 복구 중 선택한다. 자동 실행하지 않는다. |

**입력·단위·종속 조건:** length/mass/time 일관 단위, gravity vector·velocity·angular velocity/COM/frame, rigid constraints·contacts·termination/output timing·material density/rate/failure controls가 필요하다. 0.6 m 이상 자유낙하 기준 v=√(2gh)는 저항/초기회전 없는 이상화이며 측정값 대체가 아니다.

**저장·출력·재열기:** native starter/engine 또는 해당 solver 입력·includes, IC/geometry/frame, solver build·time-step controls·full requested histories와 failure outputs를 보존한다. physical video/calibration refs는 Data를 참조한다.

**오류·취소·복구:** unsupported preprocessing/conversion은 누락 card를 목록화하고 export/run 차단한다. 안정 timestep 급감/negative volume/energy jump는 실패 time과 element로 이동한다. mass scaling을 숨겨 결과를 정상화하지 않는다. 실패 값·partial outputs를 삭제하지 않는다.

**현재 코드의 재사용:** 기존 explicit/OpenRadioss 조사·bounded adapter, Simulation·Runner·Post를 재사용한다. 현재 일반 contact/rigid/composite/failure deck 전체가 구현되었다고 가정하지 않는다.

**추가·변경과 연결:** explicit typed IC/controls/output editor와 free preprocessing/exporter·parser를 연결한다. PrePoMax→inp 변환은 실제 card coverage 확인 뒤 채택하며 상용 LS-OPT 또는 유료 tool에 의존하지 않는다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. FN-12/14/17/25/27. solver 설치/explicit adapter admission은 이 실행만 막는다.

**사용자 완료 조건:** 자기 모델의 단위·IC·contact를 확인하고 실제 solver 결과의 에너지·forces·acceleration·time/failure를 저장/재열기한다. 한 benchmark로 제품 낙하 전체 수용을 선언하지 않는다.

**검증 연결:** PV-16, UI-16 IC; RG-16 card/units; NR-13 impact energy/time/force references; IT-08 explicit workflow.


### FN-17 — 파괴·계면·피로 가정을 분리해 손상 연구

**사용자 / 완료 결과:** 접착·복합재·파손 연구자 · bulk 소성, cohesive 손상, 재접촉과 반복 효과를 구별해 관측과 비교한다.

**추적:** R01, R17, R29, R30, R31 · 기존 T24, T25 · UC02, UC05, UC07

**시작 조건:** Material law와 interface/element topology를 정한 FE 모델 또는 material-point 시험으로 시작한다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. SIM-FAILURE | bulk/interface law tree·traction–separation curve, opening/sliding directions. | 강성/강도/파괴에너지·mixed-mode·damage onset/evolution을 해당 domain에서 입력한다. |
| 2. SIM-FAILURE | 압축 전달·재닫힘 contact·마찰·벌크 plasticity의 중복/누락 진단. | damage 후 압축 접촉 경로와 tied/cohesive/contact 경계를 검토한다. |
| 3. POST-CONTACT | opening/slip/damage·plastic strain·energy·failure location/time. | 계면과 벌크 반응을 따로 선택하고 결과 변화와 mesh regularization을 검토한다. |
| 4. STUDY-DECISION | 관측 박리/잔류변형·가설 지지/반박, fatigue 자료 유무. | 한 cycle 결과를 fatigue life로 쓰지 않고 별도 누적손상/시험 근거 요구를 남긴다. |
| 5. REOPEN-SIMULATION | 이 도구의 정확한 saved owner·입력·결과·누락 branch, 새 session. | 같은 도구 편집/보존 결과/영향받은 참조 복구 중 선택한다. 자동 실행하지 않는다. |

**입력·단위·종속 조건:** traction stiffness 단위(예 N/mm³), stress strength(MPa), fracture energy(N/mm), interface thickness·mode mix·regularization length·rate/temperature와 cyclic damage law의 범위를 명시한다. fatigue model/허용 조건이 없으면 life input/result를 생성하지 않는다.

**저장·출력·재열기:** law source/version·parameter source·mesh/interface mapping·damage history/energy·failure event 정의·물리 시험 ref를 보존한다. element deletion은 원 mesh identity+active mask로 추적한다.

**오류·취소·복구:** 단위·mesh 의존·negative stiffness·unsupported mixed-mode 법칙은 해당 curve/field에 표시한다. 수렴 실패와 물리 파괴를 구별한다. 접촉 재닫힘 미지원은 압축 전달이 계산되었다고 표시하지 않는다.

**현재 코드의 재사용:** Material/MFront·Simulation/native assignments·Post time/field/evidence를 재사용한다. full cohesive/failure/fatigue library는 추가 adapter/domain 범위다.

**추가·변경과 연결:** interface law/traction-separation editor, bulk/interface response comparison, damage/element activity reader와 mesh-regularization reference를 추가한다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. FN-06/08/09/14/15 또는16. fatigue는 실제 cyclic law/자료가 있을 때만 지원한다.

**사용자 완료 조건:** 동일 모델에서 bulk/interface 결과와 압축 재접촉을 구분하고 에너지·단위·mesh sensitivity를 검토한다. 시험 없는 fatigue/release는 UNKNOWN이다.

**검증 연결:** UI-17, NR-14 material/interface/fracture energy tests, RG-17 history identity, IT-07/08.


### FN-18 — CAD 없이 방정식·약형식·ODE/PDE를 편집하고 해를 비교

**사용자 / 완료 결과:** 수치해석·PDE 연구자 · 모델 식·영역·공간·조건을 바꿔 지원 backend의 해와 독립 기준을 조사한다.

**추적:** R01, R16, R28, R31 · 기존 T21, T25 · UC04, UC06, UC15, UC16

**시작 조건:** 독립 PDE에서 domain 또는 exact mesh를 선택한다. 현 registered FEniCSx 모델과 향후 사용자 weak form을 분리해 표시한다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. PDE-EQUATION | Model Builder의 domain/field/space/equation/BC/IC/mesh/solver·큰 field view. | node 선택에 따라 equation editor·field table·region selector가 바뀐다. 전체 raw settings를 한 폼에 나열하지 않는다. |
| 2. PDE-INVALID | 선택 약형식의 미선언 변수·차원·backend syntax 오류 위치. | 식 검사에서 오류 token으로 이동해 수정한다. 식 검사와 solver 실행은 별도다. |
| 3. PDE-EQUATION | boundary tags·dimension·개수·unit/mesh revision, field polynomial order. | 경계·초기조건과 function space를 선택하고 유효 input을 고정한다. |
| 4. PDE-RESULT | 해 field와 L2/H1 또는 정의한 response error·mesh levels·residual. | 해석해/다른 mesh/solver의 동일 정의와 비교하고 Post로 exact result를 연다. |
| 5. REOPEN-PDE | 이 도구의 정확한 saved owner·입력·결과·누락 branch, 새 session. | 같은 도구 편집/보존 결과/영향받은 참조 복구 중 선택한다. 자동 실행하지 않는다. |

**입력·단위·종속 조건:** independent variables/domain dimension, field scalar/vector/mixed, function space/order, coefficients, strong/weak form, BC/IC·time stepping·nonlinear/linear solver가 필요하다. 현 PDEDocuments의 declared adapters는 unit 1·bounded AST arithmetic이며 SI thermal field라고 relabel할 수 없다. 일반 dimensioned weak form·ODE는 별도 adapter 등록이다. 현재 bounded nonlinear 화면은 전체 경계 상수 Dirichlet과 정해진 diffusion형식을 사용한다. arbitrary weak form/BC type/time/space extension은 capability별 새 adapter 과제이며 기존 validator의 허용값을 바꾸지 않는다.

**저장·출력·재열기:** equation text와 parsed/validated definition·adapter/version·mesh tags/hash·solver settings·reference expression·error norm·fields/results를 저장한다. arbitrary Python을 편집 즉시 실행하지 않는다.

**오류·취소·복구:** reader/backend 없어도 식과 과거 결과는 연다. boundary missing/field mismatch·pure Neumann singularity·nullspace는 해당 모델 진단으로 처리한다. 새 일반 약형식을 기존 bounded adapter로 속여 실행하지 않는다.

**현재 코드의 재사용:** PDEDocuments, pde.update/pde.evaluate, pde_window와 current rectangle/nonlinear/transient/vector/coupled/imported adapters를 재사용한다. owner 신규 생성은 필요 없다. 추가 직접 조회한 plugins/pde_nonlinear/reference.py는 -div((1+alpha*u²)grad(u))=rhs, unit_square/P1/whole-boundary constant Dirichlet/alpha0..2/bounded RHS, 고정 Newton atol=rtol1e-10/max25다. 기존 UI에서 임의 laplace 텍스트나 정책1e-8/max50이 현재 허용된다고 표시하지 않는다.

**추가·변경과 연결:** ModelBuilder-context editor, declared expression/highlight·mesh selection을 개선하고 general weak-form/ODE/dimensioned-field adapter를 별도 확장한다. FEniCSx 우선 경로; MOOSE/GetDP 등은 해당 요구와 무료 배포 근거로 선택한다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. FN-01/02/25/27. dimensionless existing PDE 편집은 CAD·Material·Plan 없이 가능하다.

**사용자 완료 조건:** 식 수정→오류수정→domain/BC→실제 해→동일 norm 비교→save/reopen을 완료한다. 식 검사 성공을 numerical validation으로 표시하지 않는다.

**검증 연결:** PV-18, UI-18 equations; RG-18 parser/refs; NR-15 manufactured solution/mesh rates; IT-09 CAD-free PDE.


### FN-19 — 같은 Evaluation 정의로 단계·장 전달·연성 반복을 수행

**사용자 / 완료 결과:** 열–구조·멀티피직스 연구자 · Plan 없이 재사용 평가 정의를 편집하고 실제 단계 결과·전달·미수렴/복구를 추적한다.

**추적:** R01, R16, R19, R20, R31 · 기존 T25-C1, T25-C2, T25-C3, T25-C4 · UC06, UC16

**시작 조건:** 기존 kind=evaluation owner의 정의를 독립 editor로 연다. Plan에서 ‘평가 정의 편집’을 눌러도 같은 owner/editor이며 복사본을 만들지 않는다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. EVAL-STAGES | saved Material/PDE/Simulation 단계·순서·exact revision과 공개 inputs/outputs. | 단계를 추가하고 같은 표에서 삭제·순서를 바꾼다. 삭제로 끊기는 transfer를 표시하고 invalid draft로 저장 가능하다. |
| 2. EVAL-TRANSFER | 출발/도착 port·quantity/measure/unit/association/mesh/time·필수 영역. | 현재 exact_same_mesh이면 실제 metadata equality를 확인한다. K/°C 변환·mapping은 새 검증 경로가 있어야 선택한다. |
| 3. EVAL-TRANSFER | 정적 연결 검사와 공급 field 수신 값 검사를 구별한 상태. | 한 번 평가를 실행한다. 생산된 field·mask를 검사한 뒤 수신 단계를 제출한다. |
| 4. EVAL-NONCONVERGED | stage attempt·iteration residual·absolute/relative scale·최대 반복·NOT_CONVERGED. | 실패 단계 원입력 또는 동일 prefix 재사용 범위를 연다. iteration은 현 코드의 부분 loop 재사용 불가 제한을 유지한다. |
| 5. RUN-CANCEL | 전체 evaluation 취소 범위·진행 child/command·cleanup. | 후속 stage/iteration을 멈추고 actual terminal을 확인한다. 늦은 결과는 보존하며 실행을 재개하지 않는다. |
| 6. REOPEN-EVALUATION | 정의·exact refs·잔차·미수렴·부분 결과·재사용 가능 prefix. | save→새 owner reopen 후 같은 editor에서 수정하거나 명시 새 attempt를 시작한다. |
| 7. RUN-EVALUATION | 선택 기능의 job/attempt/frozen input/result, cancel scope와 실제 종료 관측. | 정확한 source editor/result를 연다. 취소 요청은 새 제출을 멈추며 terminal이 확인될 때까지 현재 실행을 보존한다. |
| 8. RUN-CANCEL-EVALUATION | 선택 기능의 job/attempt/frozen input/result, cancel scope와 실제 종료 관측. | 정확한 source editor/result를 연다. 취소 요청은 새 제출을 멈추며 terminal이 확인될 때까지 현재 실행을 보존한다. |
| 9. SIM-THERMAL | 기존 bounded SI stage V-02r4/V-03r6, metre/P1/K, Tref와 actual transfer. | 같은 Simulation owner의 정확한 stage를 연다. 일반 nonlinear 예시나 dimensionless PDE를 thermal input으로 바꿔 표시하지 않는다. |
| 10. SIM-THERMOELASTIC | 기존 bounded SI stage V-02r4/V-03r6, metre/P1/K, Tref와 actual transfer. | 같은 Simulation owner의 정확한 stage를 연다. 일반 nonlinear 예시나 dimensionless PDE를 thermal input으로 바꿔 표시하지 않는다. |

**입력·단위·종속 조건:** 현재 code는 1–32 stages, exact saved refs, transfers/bindings/responses, lag 0/1, exact_same_mesh, bounded checks를 가진다. unit/quantity/location/measure/frame/coordinate metadata가 일치해야 한다. iteration restart_safe와 초기 optional/seeded feedback이 필요하다. ‘전달 단위 변환’ 확장은 절대온도와 ΔT를 구분하고 T_ref 소유는 구조 domain에 둔다. 기존 thermal.fenicsx.rectangle→structural.fenicsx.thermoelastic_rectangle 경로는 SI steady isotropic conduction/동일 metre/global P1 triangular rectangle/완전 Kelvin nodal capture/plane-stress free expansion·명시 T_ref로 bounded다. 임의 열/PDE 변환 지원과 구별한다.

**저장·출력·재열기:** Evaluation이 stage/transfer/iteration/reuse recipe를 소유하며 domain 물리 입력과 Plan search budget은 참조한다. candidate는 frozen per-stage inputs로 파생되고 원 definition/domain을 바꾸지 않는다. stage attempt·transfer field hashes·input/output times·residuals를 retained result에 저장한다.

**오류·취소·복구:** required receiver mask가 비면 수신 solve를 제출하지 않는다. 모든 stage 프로세스가 성공해도 residual 불만족은 NOT_CONVERGED. 현 code는 동일 성공 prefix의 명시 재사용만 허용하고 iteration partial restart를 거절한다. 새로운 checkpoint 재개는 추가 지원이 검증될 때만 표시한다. 현 재사용은 full definition_sha256와 후보값도 같아야 한다. downstream stage만 바꿔도 current code의 prefix 재사용은 거절된다. 환경만 수리한 동일 정의 retry와 더 유연한 변경 후 재사용(추가 개발)을 구별한다.

**현재 코드의 재사용:** EvaluationDocuments, compile_definition/execute, evaluation.update/evaluation.run→evaluation.coupled, evaluation_window와 existing JobManager를 그대로 확장한다. owner·operation을 신규로 분류하지 않는다. 기존 thermal.fenicsx.rectangle/structural.fenicsx.thermoelastic_rectangle SI 장 전달 adapter·reference를 재사용한다. native opt-in tests 존재와 실제 실행은 별개다.

**추가·변경과 연결:** same editor의 단계/전달/반복 table, port picker·유효영역 preview·수렴/재사용 diff를 개선한다. 기존 SI 열→구조의 UI 연결을 우선하고, 범용 geometry·단위 변환/validated mapping·checkpoint 방식은 기존 서비스를 활용하는 별도 adapter capability다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. FN-18/15 등 선택 domain과 FN-25만 필요하다. Plan·Expert·모든 backend 설치를 선행으로 두지 않는다. 제한된 SI 열→구조 path를 기존 adapter로 확인하고 넓은 thermal/구조 geometry는 별도 확장한다.

**사용자 완료 조건:** 같은 Evaluation을 독립/embedded/MCP로 편집한다. 실제 열 결과→구조 수신 값을 조회해 ΔL 기준을 검증한다. NOT_CONVERGED·cancel·failed-stage reuse·cold reopen을 별도로 확인한다.

**검증 연결:** PV-19, UI-19 same editor; RG-19 reference/partial restart; NR-16 field transfer/thermal expansion/iteration; IT-10.


### FN-20 — DOE 후보를 만들고 영향도와 Sobol 분석을 구분

**사용자 / 완료 결과:** 설계 탐색·수치 연구자 · 실제 후보의 입력/결과/실패를 보고 변수의 영향과 분석 한계를 판단한다.

**추적:** R18, R27, R31, R40 · 기존 T19, T25 · UC09, UC11, UC17

**시작 조건:** 저장된 Material/PDE/Simulation 또는 Evaluation input descriptor를 Plan에서 선택한다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. NUM-DOE | 변수 ID·unit/type·model bounds와 Plan 탐색범위, response definition. | free/fixed·linear/log와 LHS count/seed/budget를 설정하고 실제 후보를 생성한다. |
| 2. NUM-DOE | candidate table·선택 점 scatter·실패 후보·원 evaluation refs. | 행/점 선택을 연결하고 후보를 실행한다. 실패/invalid 응답은 누락과 사유를 보존한다. |
| 3. NUM-SENSITIVITY | 회귀 영향도의 sample/제외·rank·condition·분석 범위 또는 Sobol의 S1/ST/CI. | LHS 회귀와 matched Sobol plan을 별도 분석으로 고른다. Sobol 샘플 순서/입력 identity를 검사한다. |
| 4. NUM-DOE | 선택 후보의 원 input/response·plot와 저장 상태. | 중간/실패 후보를 보존하고 ‘원 모델 열기/후보 채택’은 명시 동작으로 수행한다. |
| 5. NUM-CASE-DOE | 선택 candidate/analysis의 원 입력·결과·단위·validity·NOT_RETAINED 상태. | 같은 method Plan과 case를 유지해 조회한다. 행 선택은 새 evaluation을 만들지 않는다. |
| 6. RUN-NUM-DOE | 해당 named Plan/job/attempt와 새 confirmation 범위. | 명시 새 evaluation/attempt만 만들고 이전 예측/실패/요약을 덮어쓰지 않는다. |
| 7. REOPEN-NUM-DOE | 같은 Plan/method/원자료/실행 기록과 saved refs. | 같은 method 결과를 열고 재실행 없이 읽는다. engine resume 지원이 없으면 새 실행으로 제안한다. |
| 8. NUM-CASE-SENSITIVITY | 선택 candidate/analysis의 원 입력·결과·단위·validity·NOT_RETAINED 상태. | 같은 method Plan과 case를 유지해 조회한다. 행 선택은 새 evaluation을 만들지 않는다. |
| 9. RUN-NUM-SENSITIVITY | 해당 named Plan/job/attempt와 새 confirmation 범위. | 명시 새 evaluation/attempt만 만들고 이전 예측/실패/요약을 덮어쓰지 않는다. |
| 10. REOPEN-NUM-SENSITIVITY | 같은 Plan/method/원자료/실행 기록과 saved refs. | 같은 method 결과를 열고 재실행 없이 읽는다. engine resume 지원이 없으면 새 실행으로 제안한다. |

**입력·단위·종속 조건:** 현재 numerical variables는 bounds 기반 연속 변수·linear/log가 중심이다. integer/discrete/categorical·종속성은 요구 범위로 유지하되 실제 engine descriptor에 없으면 draft/unsupported다. Sobol은 현 코드 independent uniform physical coordinates·base count 2의 거듭제곱·완전한 finite output이 필요하다.

**저장·출력·재열기:** 방법/seed/후보 순서·입력/결과/실패/penalty·response definition·analysis mask·sampling matrix를 저장한다. 일반 DOE 행을 Sobol 설계로 다시 표기하지 않는다.

**오류·취소·복구:** 실패 candidate를 삭제하고 Sobol 배열을 줄이지 않는다. complete output이 없으면 Sobol analysis 차단과 필요한 재평가 행을 표시한다. cancel은 후속 후보 중단과 running cleanup을 구분한다.

**현재 코드의 재사용:** run_doe/analyze_candidates/sample_sensitivity/analyze_sensitivity·campaign_analysis·Plan owner가 이미 있다. optional SALib가 없으면 설치 미확인 표시이며 새 engine을 대체 작성하지 않는다.

**추가·변경과 연결:** typed variable/response picker·candidate↔scatter·sensitivity view를 기존 엔진에 연결한다. categorical/discrete는 별도 method capability로 확장한다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. FN-01/02/25와 선택 evaluator. 민감도 기능 전체를 최초 DOE UI의 gate로 삼지 않는다.

**사용자 완료 조건:** 복수 변수 DOE를 실제로 실행하고 행/점/원 evaluation이 동일하다. rank 결함·실패·Sobol 설계 불일치가 분석 성공으로 넘어가지 않는다.

**검증 연결:** UI-20, RG-20 candidate identity/matched design, NR-17 analytic sensitivity, IT-11.


### FN-21 — 목표·제약과 관측으로 일반 최적화·역해석 수행

**사용자 / 완료 결과:** 설계 최적화·모델 보정 연구자 · 단일 값 조정부터 여러 domain의 역해석까지 명시한 목적·제약으로 계산하고 근거와 함께 채택한다.

**추적:** R18, R27, R31, R32 · 기존 T19, T25 · UC01, UC09, UC10, UC12

**시작 조건:** Plan이 exact evaluator/domain을 참조하고 사용할 response와 관측을 선택한다. 재료 fit 전용 화면 외 일반 Request Plan을 재사용한다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. NUM-OPTIMIZE | 목적/제약 표의 quantity·unit·location/time/reduction·방향·limit. | 최소 변위/최대 강성/측정 오차 등 목적을 지정한다. 응력 peak와 average를 같은 이름으로 섞지 않는다. |
| 2. NUM-OPTIMIZE | method·bounds·budget/seed·중지 조건·parallel execution 설정. | 지원 DE/least-squares 등 실제 method를 선택하고 기준 평가를 확인한다. |
| 3. RUN-ACTIVE | 세대·평가수·best feasible·실패·실제 child attempts. | 진행을 관찰하고 필요 시 전체 취소한다. 모든 후보가 infeasible이면 그 사유를 유지한다. |
| 4. MAT-ADOPT-CONFLICT | 후보값 vs 현재 각 owner의 exact revision·changed fields. | owner별 채택 preview→유효성 검사→새 revision 또는 분기를 만든다. |
| 5. REOPEN-NUMERICAL | Plan N-05r8/sourceMaterial17·후보/실패·미보존 상세. | 계산 없이 같은 Plan·retainedfit을 열고 명시새평가와 이력열람을 구별한다. |

**입력·단위·종속 조건:** objective/constraint는 원 response 정의·unit·validity·reduction을 고정한다. 제약 위반 search penalty와 유효 물리 응답은 다른 필드다. inverse는 observation/mask/weight/normalization·허용 데이터 누락 규칙을 고정한다.

**저장·출력·재열기:** 각 후보 최소 기록, engine settings/seed/order·종료 사유·지원 checkpoint 정보, 선택 후보의 raw results/diagnostics를 보존한다. output policy가 과거 채택 근거를 삭제하지 않는다.

**오류·취소·복구:** 원 model 변경은 run input을 바꾸지 않는다. engine이 resume state를 제공하지 않으면 ‘이력 열기’와 ‘새 실행’을 명시한다. multi-owner adoption 부분 실패는 FN-02로 회복하고 selected candidate만으로 자동 채택하지 않는다.

**현재 코드의 재사용:** optimize/fit_model, NumericalDocuments 및 RequestPlanWindow, candidate adoption을 재사용한다.

**추가·변경과 연결:** typed response/objective editor·constraint/status plot·owner별 adoption preview를 보완한다. PDE-constrained/adjoint·TAO 등은 실제 gradient adapter가 필요할 때 별도 path로 확장한다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. FN-20의 variables/response UI, 선택 evaluator, FN-25. 데이터 없는 optimization에 Data/Material 의존을 만들지 않는다.

**사용자 완료 조건:** 실제 여러 변수·제약 search와 inverse를 실행하고 유효 후보를 분리한다. 바뀐 target의 stale adoption·실패·취소·재열기까지 처리한다.

**검증 연결:** UI-21, RG-21 budget/penalty/adoption, NR-18 known optimum/inverse identifiability, IT-11.


### FN-22 — 산포·상관 가정을 정의하고 UQ 결과를 읽기

**사용자 / 완료 결과:** 공차·물성 변동 연구자 · 불확실성 입력과 실패 표본의 영향을 알고 분포·초과확률을 해석한다.

**추적:** R18, R31, R32 · 기존 T25 · UC11

**시작 조건:** 평가기/변수/응답이 있는 Plan을 UQ 모드로 연다. optimizer population을 확률 표본으로 자동 재사용하지 않는다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. NUM-UQ | 분포 표: 종류·단위·mean/std/bounds·source·독립/상관 선언. | 현재 지원 uniform/normal/truncnorm/lognormal과 independence를 선택한다. 실측/문헌/가정/합성을 구분한다. |
| 2. NUM-UQ | 샘플 budget와 domain bounds 밖 예상/검사, response threshold. | 명시 샘플 생성·실행한다. normal tail을 몰래 잘라 truncate하지 않는다. |
| 3. NUM-UQ | valid/failed counts, conditional histogram/CDF·quantiles·exceedance fraction. | bar/bin 선택으로 해당 실제 sample의 입력/실패/결과를 연다. |
| 4. STUDY-DECISION | 성공 표본에 조건부인 통계와 실패율, 기준 초과·불확실한 항목. | 가정·통계 한계를 포함해 근거를 Study에 연결하고 저장한다. |
| 5. NUM-CASE-UQ | 선택 candidate/analysis의 원 입력·결과·단위·validity·NOT_RETAINED 상태. | 같은 method Plan과 case를 유지해 조회한다. 행 선택은 새 evaluation을 만들지 않는다. |
| 6. RUN-NUM-UQ | 해당 named Plan/job/attempt와 새 confirmation 범위. | 명시 새 evaluation/attempt만 만들고 이전 예측/실패/요약을 덮어쓰지 않는다. |
| 7. REOPEN-NUM-UQ | 같은 Plan/method/원자료/실행 기록과 saved refs. | 같은 method 결과를 열고 재실행 없이 읽는다. engine resume 지원이 없으면 새 실행으로 제안한다. |

**입력·단위·종속 조건:** 현재 run_uq는 independent marginals·LHS inverse-CDF, source origin/ref가 필수다. lognormal mean/std는 physical arithmetic 값이다. correlation matrix·copula·measurement covariance는 요구 범위지만 신규 method capability로 구분한다.

**저장·출력·재열기:** distribution parameters/source·sampling matrix/seed·all failed samples·threshold definition·conditioning rules를 저장한다. 성공 표본 통계만 전체 신뢰확률로 표시하지 않는다.

**오류·취소·복구:** bounds 밖 sample이면 범위 변경 또는 명시 truncnorm을 선택하고 새 Plan revision으로 실행한다. failed fraction가 높아도 무시·0 대입하지 않는다. 일정한 응답/valid<2는 std/CI를 undef로 표시한다.

**현재 코드의 재사용:** run_uq와 probability_statistics, existing Plan/Runner/candidate analysis를 재사용한다.

**추가·변경과 연결:** distribution editor·source badge·failure-aware histogram을 개선하고 상관/비정규 joint model은 별도 검증된 engine path를 추가한다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. FN-20/25와 evaluator. 서로 독립이 아닌 입력을 current independent mode로 실행할 수 있게 위장하지 않는다.

**사용자 완료 조건:** 각 분위수/초과확률에 valid count·failure conditioning과 정확 분포를 확인한다. 상관 요구가 삭제되지 않고 지원 미완료로 남는다.

**검증 연결:** UI-22, NR-19 moments/tail/conditioning/correlation, RG-22 sample identity, IT-11.


### FN-23 — 대리모델을 학습·검증하고 실제 solver 확인과 구별

**사용자 / 완료 결과:** 고비용 해석 탐색 연구자 · 보존된 해석으로 빠른 예측을 만들되 적용 범위와 holdout 오차를 확인한다.

**추적:** R18, R31 · 기존 T25 · UC13

**시작 조건:** 동일 변수/응답 의미의 train/holdout candidate tables가 있다. 실제 input point가 겹치지 않아야 한다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. NUM-SURROGATE | train/holdout run refs·rows·input ranges·model settings. | 지원 SciPy RBF 옵션을 고르고 holdout을 학습에 쓰지 않는다는 범위를 확인한다. |
| 2. NUM-SURROGATE | predicted-vs-observed·residual·MAE/RMSE/max error와 out-of-range 표식. | 오차 점→원 candidate/result로 이동해 누락/실패 또는 boundary issue를 검토한다. |
| 3. NUM-SURROGATE | 새 parameter point·support check와 PREDICTED 결과. | 예측을 요청한다. 외삽은 explicit out_of_range이며 solver result badge를 쓰지 않는다. |
| 4. NUM-OPTIMIZE | 대리 예측을 사용한 추천 후보와 실해석 미확인. | ‘실제 평가로 확인’은 새 evaluation으로 제출하고 두 결과를 보존한다. |
| 5. NUM-CASE-SURROGATE | 선택 candidate/analysis의 원 입력·결과·단위·validity·NOT_RETAINED 상태. | 같은 method Plan과 case를 유지해 조회한다. 행 선택은 새 evaluation을 만들지 않는다. |
| 6. RUN-NUM-SURROGATE | 해당 named Plan/job/attempt와 새 confirmation 범위. | 명시 새 evaluation/attempt만 만들고 이전 예측/실패/요약을 덮어쓰지 않는다. |
| 7. REOPEN-NUM-SURROGATE | 같은 Plan/method/원자료/실행 기록과 saved refs. | 같은 method 결과를 열고 재실행 없이 읽는다. engine resume 지원이 없으면 새 실행으로 제안한다. |

**입력·단위·종속 조건:** variables/order/unit·normalization bounds, physical point overlap 검사, kernel/smoothing/neighbors/degree는 실제 RBF 지원을 따른다. hyperparameter tuning에 사용한 holdout은 final independent test로 다시 표기하지 않는다.

**저장·출력·재열기:** training/holdout tables·model options/normalization/library version·validation predictions·trained artifact를 저장한다. 임의 pickle 실행을 자동 허용하지 않고 신뢰 가능한 저장 포맷/재구성 정책을 구현 때 고정한다.

**오류·취소·복구:** 학습 실패·singular matrix·범위 밖·missing response는 해당 sample/옵션에 표시한다. 재학습이 필요하면 명시 새로운 model revision으로 실행한다. reopening retained prediction은 학습 재실행과 다르다.

**현재 코드의 재사용:** fit_surrogate/Surrogate.predict와 existing analysis table/Plan owner를 재사용한다.

**추가·변경과 연결:** dataset split/validation plot·surrogate artifact/reopen·prediction/actual confirmation UX를 보완한다. GP/NN 등 대안은 요구에 맞는 별도 free method 지원이며 필수 유료 서비스는 없다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. FN-20/25; 기존 결과로 학습하면 원 solver 설치가 선행이 아니다.

**사용자 완료 조건:** holdout 오차와 extrapolation을 확인하고 새 실평가로 검증한다. 학습용 점 중복 또는 PREDICTED를 engineering PASS로 승격하지 않는다.

**검증 연결:** UI-23, RG-23 split/identity, NR-20 known functions/interpolation/holdout, IT-11.


### FN-24 — 다목적·분야별 trade-off에서 실제 후보를 비교

**사용자 / 완료 결과:** 설계 최적화·MDO 연구자 · Pareto 후보의 의미와 feasibility를 보고 여러 owner에 반영할 설계를 고른다.

**추적:** R18, R31, R40 · 기존 T25 · UC13, UC16

**시작 조건:** 두 개 이상 명시 objective를 가진 Numerical Plan과 단일/복수 분야 evaluator가 있다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. NUM-MOO | 목표별 minimize/maximize·단위·limit와 axes, infeasible 후보. | 기존 epsilon-constraint method의 primary objective와 threshold grid·총 budget를 설정한다. |
| 2. NUM-MOO | Pareto scatter↔candidate table↔선택 설계의 실제 objectives/constraints. | 같은 점의 원 결과를 열고 범위·지배/비지배·solver validity를 검토한다. |
| 3. EVAL-STAGES | 복수 분야 입력/응답 연결과 공통 변수 bindings. | MDO 평가 절차가 필요하면 같은 Evaluation 정의를 편집한다. graph 자체가 optimizer가 되지 않는다. |
| 4. MAT-ADOPT-CONFLICT | 선택 후보의 owner별 변경 목록·revision conflict. | 명시 채택 또는 새 분기로 저장한다. 점 선택·정렬만으로 값을 적용하지 않는다. |
| 5. NUM-CASE-MOO | 선택 candidate/analysis의 원 입력·결과·단위·validity·NOT_RETAINED 상태. | 같은 method Plan과 case를 유지해 조회한다. 행 선택은 새 evaluation을 만들지 않는다. |
| 6. RUN-NUM-MOO | 해당 named Plan/job/attempt와 새 confirmation 범위. | 명시 새 evaluation/attempt만 만들고 이전 예측/실패/요약을 덮어쓰지 않는다. |
| 7. REOPEN-NUM-MOO | 같은 Plan/method/원자료/실행 기록과 saved refs. | 같은 method 결과를 열고 재실행 없이 읽는다. engine resume 지원이 없으면 새 실행으로 제안한다. |
| 8. NUM-ADOPT-CONFLICT | Pareto p19 / CADr12→r13 및 Materialr17→r18 충돌, thickness13.7mm / mu1.12MPa. | 각 owner 변경을 검토해 명시 draft Apply→각 Save→group receipt 게시. 취소는 current owners와 p19 결과를 유지하며 Material fit c017로 바뀌지 않는다. |

**입력·단위·종속 조건:** 각 objective의 방향·unit·scale과 constraint semantics, epsilon grid·budget를 명시한다. 현재 method가 epsilon+DE임을 표시하고 NSGA/pymoo로 재명명하지 않는다. 분야별 coupling/gradient architecture가 없는 MDO를 ‘완전 지원’으로 부르지 않는다.

**저장·출력·재열기:** threshold별 child runs·all candidates/failed/infeasible와 nondominated set, objective definitions·selected candidate/owner adoption receipt를 보존한다.

**오류·취소·복구:** 어떤 threshold 조합이 infeasible이면 그 구간을 빈/실패로 남긴다. valid 물리값 없는 후보를 Pareto로 그리지 않는다. multi-owner 취소/부분 실패는 기존 revision 유지·새 run/명시 복구다.

**현재 코드의 재사용:** epsilon_optimize→optimize/analyze_candidates와 existing Evaluation/Plan/JobManager 재사용.

**추가·변경과 연결:** Pareto coordinate/unit axes·linked selection·trade-off inspector·multi-owner adoption. 추가 MDO architecture/OpenMDAO/pymoo adapter는 무료 조건·실제 problem role로 검토한다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. FN-19/21 관련, FN-25. 다른 최적화 방법 전체를 선행으로 두지 않는다.

**사용자 완료 조건:** 실제 후보와 Pareto 점을 상호 선택하고 infeasible 사유·원 결과를 확인한다. 분야별 의미를 유지한 채 후보를 새 revision으로 채택한다.

**검증 연결:** UI-24, NR-21 known Pareto set/MDO reference, RG-24 all-child budget/cancel, IT-11.


### FN-25 — 로컬 작업의 진행·로그·취소·재시도를 관리

**사용자 / 완료 결과:** 해석 실행 담당자 · 선택한 job/attempt의 실제 상태와 원 입력을 알고 실패나 중단 뒤 안전하게 이어간다.

**추적:** R08, R12, R20, R21, R34 · 기존 T20, T02 · UC05, UC08, UC15, UC17

**시작 조건:** Runner 바로가기 또는 domain의 Run에서 같은 기존 JobManager job을 연다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. RUN-ACTIVE | job/input/backend/host/state/attempt/elapsed/result 목록과 selected attempt 탭. | job 행을 선택해 frozen input·logs·convergence·result/원 문서로 이동한다. |
| 2. RUN-CANCEL | 선택 job 취소 vs 전체 Plan/Evaluation 취소, actual children/cleanup·지원 여부. | 범위에 맞게 취소한다. CANCEL_REQUESTED는 terminal과 다르고 창을 닫아도 job은 취소하지 않는다. |
| 3. RUN-REMOTE-LOST | 마지막 관측 시각·service restart/INTERRUPTED·process 종료 확인 유무. | 상태 재조회·연결 복구·원파일 로그 확인을 한다. 동일 작업 폴더에 자동 중복 실행하지 않는다. |
| 4. RUN-ACTIVE | failed attempt 입력 hash와 수정 필요 위치. | 인프라 retry는 같은 입력 새 attempt; 수치/물리 설정 변경은 새 run/input이다. |

**입력·단위·종속 조건:** Runner는 host/queue/workdir/resources/CPU/memory/threads·execution lifetime을 소유한다. 물리 step·solver tolerance는 domain에서 편집한다. command_id와 job_id는 type label과 조회 동작을 분리한다.

**저장·출력·재열기:** 모든 attempt의 frozen input·실제 executable/build/environment·argv record(비밀 제외)·stdout/stderr/progress·partial results·exit/cleanup/validity를 보존한다. engine 내부 작은 임시 평가를 모두 영구 job으로 늘리지 않는다.

**오류·취소·복구:** lost connection은 running/finished를 추정하지 않는다. native async command의 결과 미확인은 새 ID 자동 retry를 금지하고 상태 조회한다. late results는 원 attempt에 보존하고 취소 후 탐색을 재개하지 않는다.

**현재 코드의 재사용:** RunnerWindow, jobs/research_execution, client.status/cancel/result, native command_status/cancel를 재사용한다.

**추가·변경과 연결:** 실제 phase/time·selected-attempt monitor·log paging/search·failure navigation·close/cancel과 restart recovery UI를 보완한다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. 기존 JobManager만으로 과거 job 열기 가능. 특정 solver/provider 설치와 무관하다.

**사용자 완료 조건:** queued/running/cleanup/terminal·미확인 종료를 정확히 구별하고 입력/로그/결과를 재열기한다. 창 닫기가 solver kill이나 재제출로 이어지지 않는다.

**검증 연결:** UI-25, RG-25 cancellation race/restart/ID, IT-12 actual processes.


### FN-26 — 외부 batch·SSH/HPC 실행을 로컬 연구에 연결

**사용자 / 완료 결과:** 서버/HPC를 이용하는 엔지니어 · 외부 계산을 정확한 후보/입력과 대응하고 원격 연결 실패에서도 결과를 회수한다.

**추적:** R18, R31, R35 · 기존 T25 · UC13, UC16, UC17

**시작 조건:** 외부 solver를 직접 실행하거나 이미 권한이 있는 SSH/Slurm/PBS 자원을 선택한다. 새 과금 서버를 만들지 않는다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. RUN-REMOTE-CONFIG | local/외부파일/SSH/Slurm/PBS 경로·등록 환경·명시 probe·resource limits. | 사용할 실행 위치와 queue/resource를 고른다. 실제 지원·권한이 없으면 draft를 저장한다. |
| 2. NUM-BATCH | case/exchange/candidate IDs·values/units·input files·hash·expected outputs. | export_batch로 실행 묶음을 만든다. 이것은 solver 실행이 아니다. |
| 3. RUN-REMOTE-LOST | transfer checksum·scheduler job ID·last seen·원격 workdir/exit 확인. | 연결이 끊기면 재조회/로그·결과 회수를 재개한다. 같은 job을 다시 submit하지 않는다. |
| 4. NUM-BATCH | 돌아온 결과의 exchange/case/candidate identity·status·missing/duplicate rows. | import_batch로 검증하고 missing은 NOT_EVALUATED로 남긴다. 원래 Plan/후보에서 결과를 연다. |
| 5. NUM-CASE-BATCH | 선택 candidate/analysis의 원 입력·결과·단위·validity·NOT_RETAINED 상태. | 같은 method Plan과 case를 유지해 조회한다. 행 선택은 새 evaluation을 만들지 않는다. |
| 6. RUN-NUM-BATCH | 해당 named Plan/job/attempt와 새 confirmation 범위. | 명시 새 evaluation/attempt만 만들고 이전 예측/실패/요약을 덮어쓰지 않는다. |
| 7. REOPEN-NUM-BATCH | 같은 Plan/method/원자료/실행 기록과 saved refs. | 같은 method 결과를 열고 재실행 없이 읽는다. engine resume 지원이 없으면 새 실행으로 제안한다. |

**입력·단위·종속 조건:** host/transport/queue·resource budgets, exact input manifests·native includes, scheduler job ID/account/workdir, actual runtime build·return files가 필요하다. 경로/SSH credentials는 Adapter/안전한 사용자 credential store에 있고 연구 JSON에 넣지 않는다.

**저장·출력·재열기:** existing file_batch exchange IDs/values·manifest/hash/results를 보존한다. 원격 status/probe/transfer receipts·workdir·scheduler identity는 Runner attempt에 기록한다. remote root 변경은 explicit user configuration이지 AI 임의 권한 확장이 아니다.

**오류·취소·복구:** 부분 전송은 미완료로 남기고 hash 일치한 파일만 재사용한다. 같은 이름 다른 bytes는 새 input revision이다. scheduler status와 실제 process 종료가 다르면 미확인으로 남긴다. 큐 cancel 후 원격 job 종료 확인을 기다린다.

**현재 코드의 재사용:** export_batch/import_batch는 현재 numerical.py에 존재한다. 일반 SSH/Slurm/PBS 구현은 이번 source 조회에서 확인하지 못했으므로 EXISTENCE_UNVERIFIED이며 신규/확장 여부를 재조사한 뒤 기존 code를 우선한다.

**추가·변경과 연결:** external exchange UI와 원격 runner adapter·transfer/checksum/reconnect/probe·queue status mapping. 새 scheduler를 만들지 않고 실제 batch system에 얇게 연결한다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. file batch는 FN-20과 manifest만 있으면 가능. 원격 자원은 무료/기존 허용 환경이 있을 때만 해당 실행을 지원한다.

**사용자 완료 조건:** 다른 PC 결과를 정확 exchange/candidate로 가져오고 missing/duplicate/stale/failed를 구별한다. 원격 연결이 끊겨도 중복 제출 없이 결과를 회수한다.

**검증 연결:** UI-26, RG-26 exchange manifest/partial transfer, IT-13 actual authorized SSH/queue (환경 미제공 시 NOT_RUN).


### FN-27 — 외부 결과를 독립 Post에서 열고 필터·측정으로 분석

**사용자 / 완료 결과:** 해석 결과 분석자 · 원 solver 없이 지원 결과를 열어 field/time/선택·곡선을 다루고 분석 프로젝트를 보존한다.

**추적:** R10, R12, R13, R20 · 기존 T12, T13, T15, T02b · UC05, UC10, UC15

**시작 조건:** ParaView 바로가기 또는 Runner result에서 지원 VTU/PVD/PVSM 세트를 연다. CAD·Material·AI는 필요 없다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. POST-OPEN | reader 선택·의존파일 완전성, Pipeline/Properties·Apply, field/association/time 정보. | 파일을 선택·등록하고 reader 옵션을 Apply한다. PVSM은 분석 상태 열기로 처리한다. |
| 2. POST-MEASURE | 큰 Render view·native Slice/Clip/Warp/Contour의 pending 설정. | 3D widget과 numeric property로 편집→Apply/Reset한다. display/color/camera 변경은 native 즉시표시 의미를 따른다. |
| 3. POST-MEASURE | point/cell·ID namespace·coordinate/probe·actual time·units. | 3D/Find Data 선택을 원값 표와 연결하고 ‘측정 저장’을 누른다. solver ID가 없으면 VTK index라고 표시한다. |
| 4. POST-MEASURE | PlotOverLine/SelectionOverTime의 sample·gap·원ID/보간 표식. | 시간/경로 곡선을 저장하고 원 field·선택점으로 돌아간다. |
| 5. POST-REPAIR | 분석 저장과 Save Data/State/Image/Animation export의 대상 구분. | 관리 Ctrl+S로 analysis/save refs를 보존하고 새 ParaView session에서 연다. |
| 6. REOPEN-POST | 이 도구의 정확한 saved owner·입력·결과·누락 branch, 새 session. | 같은 도구 편집/보존 결과/영향받은 참조 복구 중 선택한다. 자동 실행하지 않는다. |

**입력·단위·종속 조건:** source/result revision·reader/version·field/component/association·physical quantity/unit/measure/frame·actual time, deformed/original coordinates·warp scale, selection definition/trace semantics가 필요하다. 파일에 단위가 없으면 UNKNOWN이지 자동 MPa가 아니다.

**저장·출력·재열기:** Post owner가 native pipeline/view·pending draft·measurement/recipe·reader dependencies·retained outputs를 보존한다. 동적 조건 selection과 고정 ID selection을 구별한다. native Save State/Save Data를 분석 프로젝트 저장과 같게 표시하지 않는다.

**오류·취소·복구:** reader 미지원/배열 누락/원자료 이동·필터 failure는 해당 branch에 남기고 정상 branch는 계속 사용한다. filter cancel이 미지원이면 cancel 접수 성공으로 꾸미지 않는다. 부분 output을 current complete로 바꾸지 않는다.

**현재 코드의 재사용:** Post bridge는 workspace operations를 실제 owner thread에 delegate한다. 기존 external/workspace/analysis/measurements/source_repair, native Apply/Undo·save를 재사용한다. 전부 새 구현으로 분류하지 않는다.

**추가·변경과 연결:** 독립 empty/open UX·field/selection/time 상시표시·측정 panel과 managed Ctrl+S routing을 보완한다. 현재 Ctrl+S native Save Data 충돌은 관리 session에서만 조정한다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. FN-01/02/33, actual ParaView reader. 원 solver 또는 Pre는 필요하지 않다.

**사용자 완료 조건:** 독립 외부 파일→필터·원값·시간/경로 측정→분석저장→새 session reopen과 누락 branch recovery를 수행한다.

**검증 연결:** PV-27, UI-27 actual ParaView, RG-27 source/view/measurement identities, NR-22 interpolation/reduction, IT-14.


### FN-28 — 다른 메시·좌표·시각·단위 결과를 검증된 대응으로 비교

**사용자 / 완료 결과:** 설계 비교·실험 상관 분석자 · A/B 원값과 변환/보간값·차이·valid mask를 구별하고 틀린 차분을 막는다.

**추적:** R10, R11, R19, R20, R34 · 기존 T14, T14b, T15 · UC09, UC10, UC16

**시작 조건:** 정확 A/B source/result 또는 measurement를 선택한다. 기본은 나란히 보기이며 차분에는 대응 조건이 필요하다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. POST-COMPARE | A/B quantity/unit/measure/association/frame/mesh/time·비교 식 B−A. | 비교할 scalar/component와 동일 응답 정의를 고른다. 불일치는 해당 셀에 표시한다. |
| 2. POST-MAP-PREVIEW | B→A target points, source linear tetra cells, valid/outside/NaN counts. | 현재 지원 same_mesh 또는 linear_tetra_b_to_a를 명시하고 실제 preview를 검사한다. closest point는 대체 방법이 아니다. |
| 3. POST-COMPARE | 원 A, A 위치의 B 보간값, B source cell·time, delta/percent 두 validity columns. | Apply로 mapping/recipe를 게시한다. A=0이면 delta는 가능할 수 있지만 percent는 undefined다. |
| 4. POST-COMPARE | 서로 다른 coordinate/time/unit 입력의 필요한 변환 chain. | 지원 converter만 explicit node로 적용한다. 미지원 tensor/시간보간/다른 element는 차이 계산만 차단하고 side-by-side/동일 게이지 비교는 유지한다. |
| 5. POST-REPAIR | A/B refs·recipe/version·mask·보존 결과·source 변경 상태. | save/reopen 후 같은 값과 mask를 확인한다. changed bytes는 새 source branch로 연다. |
| 6. REOPEN-POST | 이 도구의 정확한 saved owner·입력·결과·누락 branch, 새 session. | 같은 도구 편집/보존 결과/영향받은 참조 복구 중 선택한다. 자동 실행하지 않는다. |

**입력·단위·종속 조건:** B→A mapping·quantity+unit·measure·basis+handedness·association·mesh identity/coordinates/connectivity·time origin/sample·interpolation rule와 actual valid region이 필요하다. vector/tensor는 transform 전후 component/norm 순서를 기록한다. Cauchy↔P 또는 reference/deformed mapping은 필요한 F/J 없이 금지한다.

**저장·출력·재열기:** Post가 comparison recipe와 transform order·tolerance/unit·valid/reason masks·applied input hashes·selected sample lineage를 소유한다. 공간/시간 mask와 percent denominator mask는 별도다. 숨김은 통계 제외가 아니다.

**오류·취소·복구:** 현 native analysis.py는 scalar POINTS·linear VTK_TETRA·동일 metadata/actual timestep만 지원한다. 다른 time/unit/frame 전체 변환은 아직 확장이다. preview 이후 input이 바뀌면 apply가 stale로 거절된다. gaps/outside는 선으로 잇거나 0으로 채우지 않는다.

**현재 코드의 재사용:** analysis._validate_recipe/_mesh, OUTPUT_ARRAYS/REASONS·linear_tetra_b_to_a, workspace mapping_validate/apply/undo·source repair를 재사용한다. T14b를 새 mapping engine으로 다시 만들지 않는다.

**추가·변경과 연결:** 대응 설정·valid-mask preview·선택 원값 inspector를 개선한다. quantity/frame/time/vector/tensor/cell mapping 확장은 method별 domain validation과 native filter 연결로 추가한다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. FN-27. 기존 scalar tet 대응은 해당 범위 먼저 수용하고 고급 변환 전체를 선행으로 두지 않는다.

**사용자 완료 조건:** 지원 다른 tet mesh에서 affine 기준 s=1+x+2y+3z, B=s+0.25 mm가 A 위치에서 delta=0.25 mm가 된다. outside·A0·nonfinite는 올바른 mask; time/unit/frame mismatch는 explicit repair 또는 차단이다.

**검증 연결:** PV-28, UI-28 mapping preview; RG-28 stale/masks/order; NR-23 affine/units/time/basis; IT-14 reopen.


### FN-29 — Study에서 경쟁 가설·근거·판단·후속 연구를 관리

**사용자 / 완료 결과:** 실험·해석 연구 책임자 · 독립 연구 질문에서 증거를 비교하고 자신의 판단과 다음 연구를 보존한다.

**추적:** R02, R03, R10, R11, R13, R32 · 기존 T23 · UC06, UC12, UC14, UC15

**시작 조건:** Study 바로가기에서 빈 질문을 만들거나 기존 결과/evidence에서 시작한다. Expert나 Workbench를 요구하지 않는다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. STUDY-EMPTY | 연구 질문과 competing hypotheses 빈 목록, 자료 연결 위치. | 질문·가설·구별할 관측을 적는다. automatic discussion을 시작하지 않는다. |
| 2. STUDY-DECISION | 가설별 supporting/contradicting/inconclusive evidence·source locator/revision. | 문서·result·Data 관측·문헌 또는 Expert turn을 연결하고 원근거를 연다. |
| 3. STUDY-DECISION | 서로 충돌하는 evidence와 이전 판단, 입력 변경 영향. | 판단은 사용자 명시 편집으로 채택/보류/기각한다. 새 발언이나 fit rank가 자동으로 결정하지 않는다. |
| 4. STUDY-DECISION | 다음 관측/experiment·관련 domain/Plan·책임·status. | ‘후속 연구 만들기’로 실제 편집 가능한 domain/Plan/Discussion을 열고 Study는 exact ref만 보관한다. |
| 5. REOPEN-STUDY | 이 도구의 정확한 saved owner·입력·결과·누락 branch, 새 session. | 같은 도구 편집/보존 결과/영향받은 참조 복구 중 선택한다. 자동 실행하지 않는다. |
| 6. NUM-NEXT-TEST | 이전/현재 입력·draft·saved revision·정확한 결과와 해당 복구 상태. 같은 기능의 결과를 다른 예시로 대체하지 않는다. | 명시 Apply/Save/Cancel/재열기로 전이하며 frozen 결과는 원 입력에 남긴다. unsupported/invalid required 입력의 Run은 계속 차단한다. |
| 7. REOPEN-NEXT-TEST | 이전/현재 입력·draft·saved revision·정확한 결과와 해당 복구 상태. 같은 기능의 결과를 다른 예시로 대체하지 않는다. | 명시 Apply/Save/Cancel/재열기로 전이하며 frozen 결과는 원 입력에 남긴다. unsupported/invalid required 입력의 Run은 계속 차단한다. |
| 8. STUDY-HISTORY | 읽기전용 StudyS-02r2의 질문/판단/원 근거와 currentr3비교. | 과거판단을 읽고 현재r3로 돌아간다. 다른owner복구창을 열거나 현재판단을 자동rollback하지 않는다. |

**입력·단위·종속 조건:** 질문·대안 가설·evidence ref/locator·지지/반박 방향·판단 사유·next observation. 근거 identity 검증과 과학적 타당성 판단은 다른 상태다. release state는 현재 코드 NOT_RELEASED를 유지한다.

**저장·출력·재열기:** StudyDocuments의 question/hypothesis/evidence/decision/followup·exact saved refs를 사용한다. Workbench graph와 Discussion 발언은 독립 소유다. source 새 revision 존재 알림은 old evidence를 바꾸지 않는다.

**오류·취소·복구:** 근거 파일 미존재·hash 변경·불명 locator면 해당 evidence broken/stale를 표시하고 judgement confidence를 자동 숫자로 만들지 않는다. 부분 근거가 없어도 Study 질문/draft는 저장한다.

**현재 코드의 재사용:** StudyWindow/StudyDocuments, research_context/reference resolver와 study.update/generic lifecycle가 이미 있다. 현재 Study evidence resolver는 saved document/retained result/saved Expert turn만 지원하며 임의 literature URL은 직접 참조 kind가 아니다.

**추가·변경과 연결:** 독립 Study 화면·hypothesis-evidence matrix·decision history·followup navigation을 개선한다. Workbench 안에만 숨기거나 Plan editor로 대체하지 않는다. 원문 literature는 등록 Data/document/artifact와 locator/hash로 연결하거나 bounded evidence reference 확장과 retention 검사를 추가한다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. FN-01/02. 계산·AI·CAD 없이 독립 시작/저장이 가능하다.

**사용자 완료 조건:** 질문→경쟁 가설→지지/반박→명시 판단→후속 연구→save/reopen을 수행한다. discussion/결과 도착이 기존 판단을 자동 변경하지 않는다.

**검증 연결:** PV-29, UI-29 standalone Study, RG-29 refs/no-execution/explicit decision, IT-15.


### FN-30 — Expert의 실제 토론·반론을 편집 Plan과 결과에 연결

**사용자 / 완료 결과:** 여러 분야 근거를 검토하는 연구자 · 자료와 실제 계산에 근거한 논의를 진행하고 사용자 반론·후속 연구를 보존한다.

**추적:** R02, R03, R13, R20, R32 · 기존 T22 · UC12, UC14, UC15, UC17

**시작 조건:** 독립 Discussion을 열고 주제·자료·참여 역할을 정한다. provider 없음에서도 draft/retained discussion은 열고 저장한다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. EXPERT-DRAFT | 논점·질문 초안·자료 범위·역할, provider 미연결과 retained history. | 자료/결과 refs를 붙이고 draft를 작성한다. actual role response 요청만 inference를 사용한다. |
| 2. EXPERT-DISCUSS | 실제 author/model/provider·turn·source citation·가정/관측/계산 구분. | 논점 또는 발언 선택으로 관련 근거를 열고 특정 turn에 반론을 입력한다. |
| 3. EXPERT-DISCUSS | pause/resume·부분 발언·다음 round 범위·budget. | 일시정지는 후속 발언을 막고 기존 solver job은 별도 Runner에서 취소한다. |
| 4. NUM-OPTIMIZE | 제안된 editable Plan의 평가기/변수/응답/범위/예산과 source turn. | 같은 Plan owner에서 수정 후 명시 실행한다. 허용한 Plan budget 안의 매 후보에 재승인을 요구하지 않는다. |
| 5. STUDY-DECISION | 실제 retained result를 읽은 후속 발언과 사용자가 채택할 판단. | Discussion 발언을 Study의 근거로 연결하되 Study 판단은 별도로 편집한다. |
| 6. REOPEN-EXPERT | 이 도구의 정확한 saved owner·입력·결과·누락 branch, 새 session. | 같은 도구 편집/보존 결과/영향받은 참조 복구 중 선택한다. 자동 실행하지 않는다. |

**입력·단위·종속 조건:** provider/model/endpoint·허용 도구/자료·budget·role/topic/reply_target을 명시한다. 개발용 Pro relay와 제품 inference는 다른 경로다. 보유 구독이 임의 API credit을 의미하지 않는다. 무료 경로 미확인에서는 inference unavailable로 둔다.

**저장·출력·재열기:** Discussion이 발언·논점·역할·provider errors/partial turns·source refs·Plan/result linkage를 소유한다. 대화 속 숫자만 저장하지 않고 실제 job/result reference를 유지한다. 원문 citations는 읽은 source와 대응한다.

**오류·취소·복구:** limit/offline/expired auth/provider failure 시 draft·partial/retained turn을 보존하고 새 요청/재개를 명시한다. 유료 fallback·모델 자동 변경은 없다. 가짜 전문가 답변으로 연결 성공을 시연하지 않는다.

**현재 코드의 재사용:** ExpertWindow/DiscussionDocuments, expert.update/ask/intervene/pause/resume/advance와 existing assist/runtime/providers·discussion_plan을 재사용한다.

**추가·변경과 연결:** topic map↔turn↔source·reply/user intervention·Plan/right pane를 개선하고 실제 provider 전체 Qt flow를 검증한다. 본 시안 발언은 SIMULATED UI라고 상시 표시한다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. FN-01/02/29. 실제 Plan/result 연결은 사용하려는 FN-20/21/25 경로가 필요하지만 독립 질문 draft의 선행이 아니다.

**사용자 완료 조건:** provider가 있을 때 실제 답변→반론→계획 편집→actual result→후속 토론을 완료한다. 연결 없음·limit에서도 저장/재열기가 되며 유료 API로 우회하지 않는다.

**검증 연결:** PV-30, UI-30 discussion; RG-30 ownership/no-fallback, IT-16 actual authorized provider (이번 NOT_RUN).


### FN-31 — 선택 Workbench에서 문서 연결과 변경 영향을 탐색

**사용자 / 완료 결과:** 여러 연구 문서를 함께 관리하는 엔지니어 · 자료/모델/Plan/result/Study의 정확한 관계를 찾아 원 owner로 이동한다.

**추적:** R11, R13, R19, R33 · 기존 T23 · UC09, UC16, UC17

**시작 조건:** 기존 문서가 있거나 빈 optional Workbench를 연다. 어떤 도구도 이 graph가 있어야 시작하지 않는다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. WB-LINKS | 문서·관계 목록과 optional graph, node kind·saved revision·stale/broken badges. | 한 번 클릭은 상세, 더블클릭은 정확한 owner/editor 또는 result를 연다. |
| 2. WB-LINKS | 가능한 port/관계 종류와 전달할 exact revision. | drag 또는 ‘연결 추가’ 메뉴로 관계를 선택한다. Esc는 새 연결만 취소한다. |
| 3. WB-LINKS | 새 revision 있음 vs 원 참조 깨짐, 영향받는 Plan/Study/result. | reference를 새 revision으로 바꾸기 전에 영향/필수 변환을 확인한다. |
| 4. STUDY-DECISION | 채택된 연구 판단과 계산 계획의 별도 owner. | 원 editor에서 수정하고 돌아오면 같은 관계를 갱신한다. |
| 5. REOPEN-WORKBENCH | saved exact ownerrefs와 graphlayout. | 같은 connectionview를 열고 실제Study/Evaluationowner로 이동한다. 저장이 source문서를 수정하지 않는다. |

**입력·단위·종속 조건:** 관계는 source/target kind·exact refs·port/recipe owner·meaning을 가진다. graph 선 하나가 units/field mapping을 암묵적으로 계산하지 않는다. scheduler·optimizer 상태는 기존 Plan/Runner를 읽는다.

**저장·출력·재열기:** Workbench는 view/layout와 relation refs만 가진다. 도구 원문·physics·Plan search policy·Study 판단을 복제하지 않는다.

**오류·취소·복구:** target missing이면 정상 node는 계속 열고 해당 링크를 repair/unlink한다. reference update partial 실패는 원 refs를 남기고 owner별 결과를 표시한다.

**현재 코드의 재사용:** 기존 service/research_context/Study refs와 desktop navigation을 재사용한다. 별도 graph 실행 engine이 필요 없다.

**추가·변경과 연결:** optional connection view(QGraphicsScene + table alternative), precise ref picker·impact panel를 추가한다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. FN-01/02/29와 연결 대상만 필요하다. Workbench는 전체 도구의 선행이 아니다.

**사용자 완료 조건:** 모든 graph 동작을 목록/키보드로도 수행하고 정확 owner를 연다. 링크 변경이 다른 문서 원값을 몰래 편집하지 않는다.

**검증 연결:** UI-31, RG-31 refs/stale/drag cancel, IT-15.


### FN-32 — 결과·근거·검증 상태를 보고서와 인계로 보존

**사용자 / 완료 결과:** 연구·설계 검토 담당자 · 어떤 입력과 기준에서 무엇을 확인했는지 설명 가능한 보고서를 만든다.

**추적:** R09, R10, R11, R12, R20, R32, R34, R52 · 기존 T16, T24, T26 · UC09, UC14, UC15

**시작 조건:** Study 또는 선택 result에서 보고서 만들기를 연다. 실제 계산 없는 질문·문헌 검토도 지원한다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. REPORT-REVIEW | 선택 입력/결과/evidence·source revisions·표/곡선/그림·judgment. | 보고서에 포함할 근거와 범위를 선택하고 data provenance를 확인한다. |
| 2. REPORT-REVIEW | program/solver 종료·numerical validity·engineering check별 상태. | UNKNOWN/NOT_RELEASED와 실패값을 유지한다. 검증 기준이 없는 항목에 PASS를 자동 부여하지 않는다. |
| 3. REPORT-REVIEW | 보고서 미리보기와 데이터/그림 export 범위. | Markdown/지원 PDF·CSV/PNG 등 무료 출력으로 내보내고 native·raw refs를 함께 보관한다. |
| 4. RECOVERY-REOPEN | 보고서 artifact과 source model/results를 다시 열 수 있는 링크. | 새 session에서 근거를 열어 같은 원값/recipe를 조회한다. |
| 5. REOPEN-REPORT | S-02r3/evidence/contact-result-031/r1/F05원값을 가진 reportdraft. | 저장한 report와 sourceStudy를 다시 열고 UNKNOWN/NOT_RELEASED를 보존한다. |

**입력·단위·종속 조건:** 각 check의 validator/version·threshold/expected range·target revision·source evidence/time·blocking/reuse scope를 포함한다. 필요한 공학 기준이 없으면 사유와 UNKNOWN을 보존한다.

**저장·출력·재열기:** Core artifact/evidence/provenance를 사용한다. 보고서 자체는 새 artifact이며 source result를 고치지 않는다. plot display downsampling·filtered channels·time/mesh mappings를 caption에 표기한다.

**오류·취소·복구:** 근거 파일 누락 시 해당 section을 unavailable로 남기고 보고서 생성 오류와 engineering UNKNOWN을 구분한다. file save 실패는 이전 report+draft를 남긴다. 비공개 자료 자동 외부 전송은 하지 않는다.

**현재 코드의 재사용:** 현재 artifact/evidence/provenance/result schema 및 reports 경로를 활용하며 기존 reports engine 범위는 구현 때 file-level 추가 대조한다.

**추가·변경과 연결:** selection-based report assembly·preview/export·evidence links와 release status summary를 연결한다. 임의 디자인 승인 엔진을 새로 만들지 않는다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. FN-27/28/29 또는 독립 result. 문헌 보고서에 CAD/solver를 요구하지 않는다.

**사용자 완료 조건:** 보고서의 모든 수치가 source input/result/recipe로 연결되고 원 실패와 UNKNOWN이 유지된다. F05 원값 3.32295e-6 >1e-6을 변경하거나 전체 설계 gate로 사용하지 않는다.

**검증 연결:** UI-32, RG-32 source/report integrity, IT-17 report→original evidence.


### FN-33 — 무료 실행 환경·도구 설치 상태와 실제 지원을 확인

**사용자 / 완료 결과:** Windows 사용자·배포 담당자 · 어떤 문서를 지금 편집하고 어떤 계산을 실행할 수 있는지 비용 없이 확인한다.

**추적:** R13, R14, R15, R16, R35, R39, U§1, U§2 · 기존 T01, T04, T26 · UC15, UC16

**시작 조건:** Research 바로가기에서 필요한 기존 서비스와 사용자 작업 폴더를 찾는다. 이 요청에서 사용자 Windows 설치를 실제 확인한 것은 아니다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. SETUP-CAPABILITY | 등록 capability·adapter 범위·runtime NOT_PROBED·실제 check receipt가 별도 열. | 사용할 backend만 ‘환경 확인’을 실행한다. 목록 조회 자체는 probe/설치하지 않는다. |
| 2. SETUP-CAPABILITY | 정확 path/build/version·필수 libraries·supported operation과 probe date. | 기존 executable을 선택하고 허용된 version/library check를 수행한다. |
| 3. HOME-EMPTY | Data/Material/PDE/Study 등의 독립 진입과 native optional installation. | CAD 미설치에서도 Research와 과거 결과를 연다. |

**입력·단위·종속 조건:** Qt Research Python과 FreeCAD/ParaView bundled Python/Qt는 별개다. 사용자 보고 환경은 Python3.13 PySide6 6.9.1+Matplotlib이며 private runtime venv의 PySide 유무를 혼동하지 않는다. 사용/배포 mode별 exact dependency license가 필요하다.

**저장·출력·재열기:** host/environment별 probe receipt·executable/version/check kind/time·license notice inventory를 저장한다. 경로/build 변경 후 옛 receipt는 historical이며 현재 readiness로 쓰지 않는다.

**오류·취소·복구:** missing runtime/provider limit는 해당 Run만 unavailable. 새로운 유료 tool/trial/API/hosting으로 fallback하지 않는다. 설치 권한/무료 경로가 없으면 현 자료 편집을 유지하고 미확인 항목을 남긴다.

**현재 코드의 재사용:** start_cae_research.ps1, existing launch contexts·backend_readiness/client·registered capabilities를 재사용한다. 본 요청의 도구 설치/사용자 Windows MoAI 연결은 Codex 환경에서 확인할 항목이다.

**추가·변경과 연결:** tool-specific shortcuts/open routing·capability matrix/readiness receipt·packaging/license checklist를 구현한다. QWidget/Matplotlib로 구성하고 QtCharts/WebEngine/유료 UI는 추가하지 않는다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. 각 독립 도구 최소 요구만 준비한다. 전체 solver install은 제품 시작 gate가 아니다.

**사용자 완료 조건:** 미설치 도구를 준비됨으로 표시하지 않는다. 실제 사용권·라이선스가 확인된 무료 경로로 실행하며 Windows 100/125/150/200%에서 readable/focus/file paths를 확인한다.

**검증 연결:** PV-33 license review, UI-33 clean Windows/DPI, IT-18 install/open/readiness.


### FN-34 — GUI·CLI·Python·선택 MCP에서 같은 문서와 명령 사용

**사용자 / 완료 결과:** GUI 사용자와 자동화 연구자 · 자연어/스크립트로 수행한 작업을 실제 열린 문서에서 확인하고 동일 결과를 분석한다.

**추적:** R02, R13, R19, R20, R21, R43 · 기존 T02, T05, T12, T16 · UC15, UC17

**시작 조건:** 기존 client/service·native host/doc/session을 조회한다. 자동화는 선택이며 일반 GUI에 MCP/AI를 요구하지 않는다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. CLIENT-CONFLICT | 현재 owner/session/generation·pending native Task 또는 cell editing. | 변경 전 fresh owner inspect로 실제 대상을 읽고 typed domain command를 보낸다. |
| 2. PRE-DESIGN | 같은 native 치수/selection과 command receipt. | 실제 owner handler가 변경한 값이 GUI에 반영되는지 확인한다. 복제 headless 파일 변경을 열린 GUI 변경으로 말하지 않는다. |
| 3. RUN-CANCEL | command_id vs job_id·queued/running/applied/result unconfirmed. | 응답 유실 시 동일 ID status 조회; 같은 ID 다른 payload는 거절한다. 옛 session mutation은 거절한다. |
| 4. POST-MEASURE | 정확 input/result/recipe/field/time/selection의 partial values. | 큰 배열은 metadata·선택 범위·파일 artifact로 읽고 사람과 AI의 ID/원값을 대조한다. |

**입력·단위·종속 조건:** current APIs의 document_command operation/arguments·session_id/expected_generation·command_id 계약을 유지한다. raw eval/module/shell 경로 대신 advertised typed commands만 허용한다. read-only cached 상태와 fresh native inspect를 구별한다.

**저장·출력·재열기:** command receipt·request hash·applied/final/current generation·view state·result identities를 보존한다. 연구 파라미터에 native 경로/인증을 노출하지 않는다.

**오류·취소·복구:** BUSY_EDIT·STALE·response loss·application unknown은 사용자의 변경을 보존하고 다시 조회한다. native 취소 미지원·오래된 command는 자동 replay하지 않는다. service scope file registration에 가짜 document ID를 만들지 않는다.

**현재 코드의 재사용:** workbench_mcp.py/client/routes·document/native handlers·local registration wrapper가 이미 있다. v2의 ‘모든 wrapper 신규’ 표는 현 pin에 적용하지 않는다.

**추가·변경과 연결:** advertised command별 UI/CLI/Python/MCP parity와 error payload·capability discoverability를 보완한다. 새로운 common controller/optimizer는 추가하지 않는다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. 해당 기능 owner와 그 명령만 필요하다. 모든 wrapper 구현을 첫 UI의 gate로 두지 않는다.

**사용자 완료 조건:** 같은 문서에 GUI→CLI/MCP 읽기와 typed edit→GUI 확인을 수행하고 stale/BUSY/두 host·응답유실을 올바르게 처리한다.

**검증 연결:** RG-34 command identity/idempotence, UI-34 actual same-window roundtrip, IT-19 optional client.


### FN-35 — 실제 실험장비 연동과 교정 반복을 지원 범위로 유지

**사용자 / 완료 결과:** 실험 자동화 연구자 · 장비가 준비된 환경에서 계획→실험→측정→보정의 반복을 정확히 기록한다.

**추적:** R01, R31, R32, R35 · 기존 T25 · UC12, UC16

**시작 조건:** 파일 기반 측정 경로 FN-05는 이미 독립적으로 사용한다. 실제 장비 제어는 user-provided device/driver·기존 사용권·명시 권한·물리 안전조건이 있을 때만 추가한다.


| 단계·화면 | 보고 판단하는 대상 | 조작과 결과 |
|---|---|---|
| 1. DATA-CALIBRATION | experiment plan·specimen/device/calibration refs와 기록할 채널. | 장비 입력/출력 계약과 수집 단위·time synchronization을 정의한다. |
| 2. DEVICE-PLAN | 장비 connection 상태·capability·control limits/interlocks·허용 실험. | read-only 확인/수집 준비를 수행한다. 실제 actuator 동작은 현재 권한/환경이 확인된 명시 실행으로만 요청한다. |
| 3. RUN-ACTIVE | 실험 attempt·실제 장비 state·수집 phase·stop/ack 여부. | 수집·중지·장비 종료 확인을 기록한다. solver job cancel을 hardware emergency stop으로 대신하지 않는다. |
| 4. STUDY-DECISION | 새 Data/교정 결과와 예측·모델 후보·다음 시험. | FN-05/21의 보정과 Study 판단을 이어 저장한다. |

**입력·단위·종속 조건:** 실제 device protocol/driver·calibration/limits·sampling rate/timestamps·actuator/measurement roles, stop/cleanup acknowledgment와 data provenance가 필요하다. 제공되지 않은 장비·안전 규약은 설계 미결로 남긴다.

**저장·출력·재열기:** 실험 plan/attempt·device raw streams·calibration/time alignment·operator/event receipts를 같은 artifact/evidence 계층에 연결한다. 원시 데이터와 모델 교정 이전본을 보존한다.

**오류·취소·복구:** device disconnected·partial acquisition·stop unconfirmed는 실제 상태 미확인으로 표시한다. 장비 동작을 추측하거나 무인 retry하지 않는다. 파일 기반 교정 작업은 계속 가능하다.

**현재 코드의 재사용:** 공통 evidence/Runner record·Data import·Study/Plan을 재사용한다. 특정 장비 driver/실제 control 구현은 이번 확인 범위에 없으며 요구를 삭제하지 않는다.

**추가·변경과 연결:** 장비별 Adapter capability와 실험 protocol/domain rules, acquisition/state/stop receipts를 추가한다. raw shell command로 임의 장비를 제어하지 않는다.

**의존·순서:** 구현 선행은 IMPLEMENTATION_BACKLOG의 task별 implementation_prerequisites를 따른다. 실행 환경 조건은 runtime_prerequisites에 별도 기록한다. 관련 기능 전체 완료를 이 도구 편집의 선행으로 삼지 않는다. FN-05/25 및 실제 장비·driver·허용 조건. 전체 제품 기획·GUI와 파일교정의 선행이 아니다.

**사용자 완료 조건:** 권한 있는 실제 장비가 준비되면 plan→data→calibration→model revision→next test와 중지/복구를 수행한다. 그 전 상태는 NOT_VERIFIED/NOT_RUN이며 fake device result를 만들지 않는다.

**검증 연결:** PV-35 interface planning, RG-35 replayed recorded IO, PH-01 actual authorized device integration (이번 NOT_RUN).


## 상세 계약 부록

### C01. 복수 owner, 셀 입력, 저장·닫기와 다른 client

Material+Plan 창은 같은 `MaterialDocument`와 `NumericalDocument`에 연결한다. 문서 두 개의 독립 수명을 한 창에 보여준다. 예시는 `Rubber · r17 · draft g42`와 `Fit A · r8 · draft g21`이다. 계수 `현재값`은 파랑 Material, `Plan 시작값/하한/상한/자유`는 보라 Plan 머리글이다. 색과 함께 owner 이름/아이콘/도움말을 쓴다.

| 사용자 행동 | 정확한 변경·결과 | 실패·되돌리기와 다음 행동 |
|---|---|---|
| Material μ 셀에 `0.9e`를 입력 | 셀 buffer에 문자열 보존. 계산에 사용하지 않음. Enter는 parse 진단, Esc는 편집 시작값으로 복귀 | `입력 마침/원문 초안으로 보존/입력 취소`를 셀에서 선택. 현재 owner가 invalid raw draft를 지원하는 필드는 원문으로 commit 가능; 숫자0 대체 금지 |
| 유효한 μ=.90 MPa Enter | `material.update` 한 변경, Material g43 dirty. Plan r8 source는 r17 그대로 | Undo 메뉴 `Material: μ 변경 취소`. Plan Undo와 혼합하지 않음 |
| Plan 상한1.4→1.2 입력 | `numerical.update` 한 변경, Plan g22 dirty. Material 허용 범위/현재값은 불변 | Undo 메뉴 `Fit A: μ 상한 변경 취소` |
| 여러 owner 열에 붙여넣기 | 적용 미리보기에서 Material/Plan 값과 영향 분리; owner별 validation/CAS 후 receipt 표시 | 한 owner만 성공하면 성공/실패 행 분리, 전체 성공 toast 금지. 실패 buffer는 남고 성공은 자기 Undo 가능 |
| Ctrl+S | 포커스 owner 저장. 제목과 버튼은 `Save Material` 또는 `Save Plan`. `Save workspace drafts…`는 별도 명령 | native 미확정 Task/유효하지 않은 buffer는 먼저 위 선택. 뜻을 보존할 수 없는 buffer는 recovery capsule로만 보존하고 saved revision이라고 부르지 않음 |
| 두 문서 저장 | Material r18 게시 성공, Plan 저장파일 쓰기 실패이면 `SAVE-PARTIAL`: Material r18 ✓ / Plan r8 + dirty g22 ! | 두 문서가 함께 저장되었다고 표시하지 않음. `Retry Plan / Save Plan branch elsewhere / Keep working`. 이전 Plan r8과 현재 dirty 유지 |
| 저장한 Material을 Plan에 반영 | `Refresh source…`에서 r17→r18, μ .85→.90, protocol/observations/변수 시작값 차이 표시. `Use new source + copy selected starts` 또는 `Keep current Plan` | 갱신은 Plan의 명시 한 변경. source 재검증·진단 후 Plan 저장. Material 저장 성공만으로 source/ref/Plan starts 자동 변경 금지 |
| 다른 client가 같은 μ 수정 | owner의 expected generation/session 확인. 미확정 겹침은 BUSY_EDIT, 기존 세대는 STALE_DOCUMENT | `CLIENT-CONFLICT`에서 Base r17 / Local buffer / Current r18 비교. `Read current`, `Propose on r18`, `New branch`, `Cancel`. 유효한 최신 대상과 새 command ID로만 명시 재제안 |
| 창 닫기 | `CLOSE-DIRTY` 표에 각 owner buffer/draft/saved, 미저장 항목, 진행 job이 각각 표시 | `Save selected and close`, `Keep recovery drafts and close`, `Discard selected changes and close`, `Return`. 실패 owner 있으면 닫기 중단. job cancel은 별도 checkbox 기본 OFF |
| 닫기 후 다시 열기 | 새 owner process에서 정상 saved revisions와 별도 recovery 후보를 제시. recovery를 선택하면 새 dirty session | 자동 solver/fit/provider 재실행 없음. 버전 미지원은 보존 결과 읽기/원문 export; 원본 migration은 사본 검증 후 명시 전환 |

`Keep recovery drafts`의 capsule은 문서 ID/base revision/session/generation, raw buffer의 cell locator/원문/단위, acknowledged draft, 참조 해시, 미결 save receipt, 보존 결과 refs를 가진다. capsule 쓰기 실패면 닫기를 완료하지 않는다. 이것은 제품 설계이며 planning prototype의 로컬 JSON 복구와 production crash durability를 동일시하지 않는다. 공통 서비스의 기존 immutable revision 쓰기/verification/committed pointer를 재사용하고 per-owner 성공을 정확히 표시한다. 실제 복수 owner adoption은 모두 검증·준비 후 adoption-set 참조를 마지막에 게시하는 확장이다. 네트워크/디스크 실패 때문에 자동 rollback 성공을 주장하지 않는다.

### C02. 두 CSV에서 Material fit까지의 물리·관측 계약

시안의 모든 값·곡선은 `data/README.md`에 정의한 합성 자료다. A/B는 같은 시편을 임의 분할한 데이터가 아니라 서로 다른 합성 specimen이다. B 전체를 holdout으로 정한 뒤 fit 예산을 고정한다. 실제 장비 데이터를 가진 것으로 표시하지 않는다.

| 원본 | 실제 열 순서 | 사용자가 DATA-MAP에서 지정 | 수치 변환·출력 |
|---|---|---|---|
| tensile_A.csv | time_s, force_N, extension_mm, temperature_C | time/time axis, force, extensometer extension, absolute temperature | t[s]=raw; F[N]=raw; ΔL[mm]=raw; T[K]=T[°C]+273.15 |
| tensile_B.csv | extension_um, temperature_K, load_kN, time_ms | extension, absolute temperature, force, time | ΔL[mm]=raw×.001; T[K]=raw; F[N]=raw×1000; t[s]=raw×.001 |

열 이름 변경/metadata의 단위 지정은 수치 변환과 다른 명령이다. 자동 추정은 미리보기이며 사용자가 확인한다. 같은 이름 Stress/strain으로 measure를 추정하지 않는다. 필수 역할 중복·누락, unit dimension 불일치, time 비단조는 해당 열/행에 표시한다. ΔT에는273.15 offset을 적용하지 않는다. 원본/행 식별/채널 ID는 유지하고 recipe output으로 canonical channel을 만든다.

시험 geometry는 `L0=50 mm`, `A0=20 mm²`; displacement 의미는 **extensometer gauge extension**이다. crosshead 변위만 주어졌을 때 이를 gauge strain이라고 바꾸지 않으며 machine compliance/게이지 위치가 없으면 해당 관측을 미확인 또는 직접 force–displacement로 남긴다. 관측은 `e=ΔL/L0`, `λ1=1+e`, `P11=F/A0`로 계산한다. 여기서 P11 단위 `N/mm²=MPa`, measure=`first_Piola`, frame=`material_cartesian`, 축은 시간[s]에 대응한 이력이다. 곡선 표시 x축 e와 evaluator 이력의 독립축 time을 구별한다. loading/unloading에서 같은 e가 반복되면 e로 정렬해 시간 이력을 잃지 않는다.

Cauchy 변환은 `σ11=(λ1/J)P11`이다. `J`는 실제 transverse 측정/완전한 F 또는 명시 가정에서 얻어야 한다. 면적 일정 또는 비압축성 J=1을 기본값으로 넣지 않는다. `ln λ1`은 λ1>0에서만 유효하다. 축별 strain/stress measure, 좌표 방향, 관측 위치를 함께 저장한다.

`MAT-PROTOCOL`은 다음 둘을 눈에 보이게 구별한다.

| 시험/평가 종류 | 입력·기본값·종속 조건 | 현재 코드 / 새 구현 |
|---|---|---|
| Prescribed deformation gradient | 모든 Fij 무차원; off-diagonal 기본0, F22/F33 기본1, F11=1+e; t 단조; detF>0 | 기존 FELUPE adapter. 이 default는 횡변형 구속이며 traction-free가 아님 |
| Uniaxial traction-free | F11 prescribed; lateral target P22=P33=0 MPa, initial λ2=λ3=1, 허용오차·최대반복은 지원 evaluator가 소유 | mixed-control material-point solve/실패 진단 추가. 현재 adapter의 capability 없는 경우 draft 저장 가능, 실제 Evaluate/Fit 차단 |
| Measured transverse history | t와 F22/F33 또는 횡 strain measure/방향 채널, 유효 구간/uncertainty | mapping + full F validation; 관측값 누락을1로 채우지 않음 |

합성 시안의 후보 비교는 traction-free protocol을 의도한 **SIMULATED** 결과다. 이는 현재 FELUPE adapter가 그 시험을 실행했다는 증거가 아니다. 현재 지원 prescribed-F 시험을 별도로 선택하면 그 이름과 기준으로 직접 평가를 할 수 있다. `.ui` 또는 화면의 버튼 enabled는 planning state이며 실제 capability gate 통과가 아니다.

### C03. 구간·mask·학습·holdout·잔차와 상세 결과 보존

DATA-EDIT에서 row40..110을 선택하면 곡선 구간과 정확 sample ID가 동시에 강조된다. 표의 정렬·열 이동 뒤에도 선택 의미는 sample ID로 보존한다. 곡선 brush는 time 범위인지 row 집합인지 작은 mode control에 표시한다. Ctrl 클릭 추가, Shift 연속범위, `Exclude quality`/`Restore quality` 컨텍스트 메뉴와 메뉴 대안을 둔다. 렌더링 decimation과 실제 계산 sample count를 다르게 표시한다.

| mask/선택 | owner | fit에 대한 의미 |
|---|---|---|
| 원자료 품질 mask, 센서 포화 등 | Data | 근거와 원값 남김; 사용불가 원행 제외 |
| 변환 유효성, det/로그/보간 support | recipe owner | 연산 불가를0으로 채우지 않고 제외 사유 보존 |
| 학습 구간/관측 선택 | Plan | 이번 연구 objective의 고정 sample selection |
| train/holdout | Plan experiment | holdout은 목적함수에 들어가지 않음 |
| 숨김, legend mute | View | 통계/fit 제외가 아님 |

실행 전 compiler가 `quality ∩ operation-valid ∩ Plan inclusion`을 채널의 안정 sample ID→원행→imported index로 매핑하고 고정한다. 현재 Data quality_rows와 Numerical Plan의 schema/compiler는 이 계약을 완전히 제공하지 않는다. 이를 **실제 추가 schema/compiler 작업**으로 backlog에 배정한다. 화면에서 줄을 회색으로 칠하는 것만으로 제외를 구현했다고 하지 않는다.

기존 curve alignment와 residual은 유지한다. 관측 e의 사용 sample 수를 n_e, curve weight를 w_e>0, scale을 s_e>0라 하면:

`r_ei = (prediction_ei − observation_ei) × sqrt(w_e / n_e) / s_e`

`objective = Σ_e Σ_used_i r_ei²` (train experiments만).

scale은 선택 응답 단위(예시0.05MPa), residual은 무차원이다. raw residual ΔP[MPa], RMSE[MPa]와 scaled residual/objective를 별도 탭에 표시한다. curve별 n으로 정규화하므로 sample 수가 많다는 이유로 곡선이 자동 우세하지 않는다. 화면에 이미 n 정규화가 적용됨을 짧은 formula tooltip으로 밝힌다. 기본 w=1, scale=1 response unit은 기존값이며 실제 시험 noise/uncertainty와 같다고 부르지 않는다. uncertainty를 기반으로 s를 채우는 동작은 값/출처를 명시 승인한 편집이다.

현재 정렬은 단조 named axis/unit 일치와 명시된 구간의 linear interpolation이다. 외삽 금지. 계산 gap이 있으면 exact sample만 허용한다. Post의 별도 시간·공간 비교 recipe를 fit 정렬로 재사용한 것으로 표시하지 않는다. 비단조 이력은 time 축으로 유지한다. 무효 sample count, 제외 사유, actual n, 양 끝 support와 gap을 실행 전에 표에서 확인한다.

`MAT-FIT-PARTIAL`의 후보표에는 물리 응답/objective/검색 penalty/실행 상태/곡선 보존/holdout을 별도 열로 둔다. 코드의 현 한계는 arbitrary candidate의 모든 상세 곡선과 holdout을 보장하지 않는다는 것이다. 최종 선택 후보에 대해서만 보존된 상세와 holdout이 있을 수 있다. 따라서 예시는 다음과 같다.

| 후보 | train objective | 실행/곡선 | holdout | 가능한 다음 행동 |
|---|---|---|---|---|
| c017 μ=.862 | 0.00184 | valid / retained selected result | evaluated, RMSE .014MPa (합성 예시) | 원값/잔차 확인 → 채택 제안 |
| c014 μ=.901 | 0.07908 | valid summary / NOT_RETAINED | NOT_EVALUATED | `Evaluate details + holdout…`로 새 evaluation과 별도 예산/기록 확인 |
| c009 | — | evaluator failure / 실제 진단 보존 | NOT_EVALUATED | 실패 입력/로그 → 수정 또는 새 평가 |
| c021 | — | CANCELLED / partial retained | NOT_EVALUATED | 보존 부분만 열기, 탐색 자동 재개 없음 |

후보 클릭/정렬/재열기는 계산을 발생시키지 않는다. 추가 평가는 `detail_eval` 새 ID로 원 후보에 연결하고 원 실행의 기록을 소급 채우지 않는다. 실제 실행이 없으면 위 숫자는 UI fixture임을 유지한다. 실행 전 retention policy에서 최소 모든 후보 입력/상태/응답/진단/기존 refs를 보존하고 선택/비교/채택 근거의 상세가 없으면 보존까지 완료한 뒤에만 해당 행동을 완료 처리한다. 메모리 cache8 항목을 영구 보존 계약으로 오인하지 않는다.

### C04. 후보 채택과 실행 입력의 고정

시안의 Material r17 μ=.85에 대한 c017 μ=.862가 도착했지만 다른 client가 r18 μ=.90을 저장했다. `MAT-ADOPT-CONFLICT`는 base .85 / candidate .862 / current .90, source result/Plan revision, 바뀐 대상과 지원 law를 같은 표에 보여준다. `Use candidate on current r18`은 r18을 읽어 새 변경 제안으로 prepare하고 기대 generation을 다시 검사한다. `New Material branch`는 새 문서 ID, `Cancel`은 현재 r18과 후보를 모두 유지한다. 버튼을 누르기 전 current 값을 바꾸지 않는다.

Model current 값, Plan 시작값, source ref는 별개다. Material r19를 저장한 후 `Refresh Plan source`에서 명시 갱신·변수 연결을 검증한다. 후보가 바꿀 수 없는 derived/read-only 변수와 native domain 허용범위는 유지한다. 복수 owner adoption은 각 owner 준비 결과를 표로 보고, 실패 owner가 있으면 publication을 멈춰 prepared 결과와 원본을 보존한다. 낙관적 CAS를 원격 분산 transaction 보장이라고 부르지 않는다.

### C05. 사용자 면 접촉의 입력·결과·형상 변경 복구

`PRE-CONTACT`의 native3D에서 selection filter=`Face`, 대상범위=`Active Analysis`, setA=`Pad underside`, setB=`Base top`을 선택한다. 목록 Add/Remove, 화면 클릭, tree 선택, Ctrl/Shift와 `Select listed faces` 키보드 대안을 동일 handler로 보낸다. 시안은 A4faces320mm², B2faces336mm², 정확 geometry r12이다. 면 번호 대신 instance/object/subshape와 geometry revision을 저장하며 번호는 표시 보조다.

| 입력/조작 | 형식·unit·기본·범위 | 의존·진단/다음 행동 |
|---|---|---|
| Contact type/law | 지원 enum, 기본 미선택; frictionless/Coulomb/tie/cohesive 중 adapter manifest가 실제 지원한 값만 실행 | 보이지 않게 삭제하지 말고 unsupported row+이유·대안·draft 유지 |
| μ | 무차원 finite ≥0, Coulomb 선택 때 필수. 예시.15는 fixture값이며 제품 default 아님 | frictionless에서는 disabled/display0 convention; tie에는 μ 적용 안 함 |
| Initial gap | 길이/단위, geometry-derived 또는 explicit policy 선택; 시안.20mm | 자동 측정값/설정값 구별. 음수는 initial overclosure이며 adapter 정책/최대허용 명시, 무조건 abs 처리 금지 |
| Normal | geometry-derived oriented vector와 flip action, A→B 화살표 | 노멀 normalization/기저·접촉 convention; flip이 바꾸는 부호와 gap 예측을 미리보기 |
| Search/tolerance/stiffness | 단위·의미·허용범위는 선택 solver law schema에서 제공, 기본 공란/adapter default 명시 | penalty stiffness를 μ와 같은 무차원 입력으로 취급 금지. 숨은 자동 tuning 없음 |
| Interaction step | 정확 step/time interval, sliding finite/small 등 지원 enum | tie와 분리 contact의 계면 의미를 섞지 않음. friction/thermal/damage coupling capability 별도 |

`Validate contact`는 set ownership/empty/overlap/normal/gap·mesh face correspondence·law/element/step/출력 가능성 검사다. `PRE-CONTACT-UNSUPPORTED`는 현재 bounded structural frozen input이 contact를 admit하지 않는 사실과 현재 adapter/runtime 행을 보인다. `Save draft / choose supported adapter / inspect missing capability`를 제공하며 unrelated material/PDE 작업은 계속 가능하다. 등록 capability와 실제 probe, 수치검증 수준은 다른 열이다.

현재 bounded benchmark를 사용자 contact 완료라고 부르지 않는다. 추가 구현은 set→surface export, law cards/friction/gap/normal, compatible mesh pairing, preflight, 실제 결과 parser와 time/association/convention 보존까지다. 면변수·normal이 필요하지 않은 solver라도 UI 의미와 exporter convention의 대응을 명시 검증한다.

결과 `POST-CONTACT`는 exact input r12/run/attempt/result/actualt=.040s를 고정하고 contact pair를 고른다. 압력[MPa] contour, normal force[N]와 tangential force[N] 시간곡선, gap[mm]/penetration[mm]/slip[mm] 선택 표를 제공한다. pressure는 surface/cell/nodal 어디 값인지, resultant force 적분인지 원 solver 출력인지, normal sign convention을 metadata로 보인다. 존재하지 않는 slip 배열은 `NOT_AVAILABLE`로 남긴다. 변형 표시 배율과 contact gap 수치를 혼동하지 않는다. 실패/미수렴 frame은 빈구간이며 성공구간을 보존한다.

저장 후 geometry r13에서 A의1면이 둘로 나뉘고 B normal이 반전된 예시는 `PRE-CONTACT-REBIND`에서 Old ghost와 New를 겹쳐 표시한다. 각 행에는 old/new instance,개수,면적,중심,normal dot,ambiguity,impact(conditions/mesh/results)를 둔다. one→many 선택은 새 두면을 모두 목록에서 확인하고 면적320→319.8mm² 차이를 표시한다. normal dot=−1은 숫자와 화살표를 함께 표시하고 재확인한다. same face number/nearest location만으로 자동 수리 금지. `Preview rebind`는 buffer; `Apply selected`만 새 contact draft 한 변경; `Cancel`은 기존 r12 refs와 r13 unresolved 상태를 그대로 유지한다. unresolved required faces면 run/export 차단, draft save 가능. 이미 계산한 r12 결과는 그대로 reopen한다.

### C06. Post 비교의 연산 순서와 유효영역

기존 pin의 실제 첫 경로는 scalar POINTS, 정확한 같은 mesh 또는 선형 tetra B→A, 동일 unit/metadata/actual time이다. 단위 변환/벡터·tensor 기저/시간보간/다른 element 일반화는 별도 개발이다. `POST-COMPARE`는 각 단계의 현재 capability를 보이며 미지원은 side-by-side 관찰까지 가능하다.

| 순서 | 필요한 결정 | 저장하는 근거 |
|---|---|---|
| 1 | A/B exact result/revision, quantity·measure·location 확인 | arrays/source hashes·공학 의미, Point/Cell/Integration 식별 |
| 2 | 필요한 quantity/단위 변환 | scale/offset·absolute/delta 의미·원값. 변환 미지원이면 차분 차단 |
| 3 | coordinate/basis 변환 | source/target frame, transform, vector/tensor 법칙. scalar엔 불필요한 방향 필수입력 없음 |
| 4 | 실제 time 대응 | exact 또는 명시 linear-common interval; 외삽/gap 금지; 각 값 original/interpolated flag |
| 5 | B→A 공간 대응 | 방법/버전/element/검색 tolerance·포함 predicate·coverage·출발 B cell. 원 ID를 interpolate하지 않음 |
| 6 | 성분 또는 norm, mask intersection | `norm(B−A)`와 `norm(B)−norm(A)` 선택 의미, source/destination invalid 사유 |
| 7 | Δ=B_at_A−A, %=100Δ/abs(A) | 비교식/분모/operation order와 두 mask·각 값 origin |

`delta_valid = meaning_valid ∩ time_valid ∩ spatial_valid ∩ finite(A,B,Δ)`.
`percent_valid = delta_valid ∩ (A != 0) ∩ finite(percent)`.
A=0이면 Δ는 유효할 수 있고 percent만 undefined다. user threshold를0 대신 편의상 epsilon으로 바꾸지 않는다. threshold/near-zero policy 추가가 필요하면 별도 명시 recipe 개정이다. 누락/밖/NaN은 invalid reason과 undefined 값으로 유지하며 통계에는 제외 수·유효면적/점수·선택범위를 보인다. 유효영역 비율만 높아도 중요한 게이지 위치가 밖이면 그 metric은 불가다.

검토 fixture의 affine 식은 s=1mm+x+2y+3z, B=s+.25mm. 내부점의 Δ=.25mm, A=2mm면12.5%; 밖 점은 invalid. 물리값 A0인 별도 scalar fixture에서는 Δ=.25mm/%undefined를 확인한다. 이는 자체 검증 fixture이며 nonlinear 실제 field accuracy 또는 사용자 mapping의 승인이 아니다.

### C07. 같은 내용 이동과 changed-content branch

`POST-REPAIR`/`RECOVERY-REOPEN`은 source별 old path/new path/hash/dependency completeness/affected branch를 보여준다. 먼저 정상 branch와 보존 수치를 연다. `Find replacement`는 승인 root 목록의 파일 선택/등록을 호출하며 ID/URL을 손으로 입력시키지 않는다. chooser를 열었다는 이유로 root 권한을 확대하지 않는다.

동일 파일 내용·지원 의존집합이면 위치 mapping을 새 saved revision에 게시하고 과거 input identity를 유지한다. PVD 한 frame bytes가 다르면 changed row와 영향 time/measurement/comparison을 표시하고 **새 source/input revision 또는 branch**로만 등록한다. 원 ref를 새 bytes로 바꾸지 않는다. 다중 원파일 중 일부만 수리된 경우 정상 branch만 live, 누락 branch는 retained view/미가용으로 남긴다. 현재 Post의 exact VTU/PVD same-content 수리·PVSM rewrite 제한을 재사용하고 일반 reader/변경내용/portable workflow는 추가 작업이다.

Research는 기존 store의 document/revision 형식, Pre는 기존 `.caepre`와 native FCStd/의존세트, Post는 관리 metadata+PVSM+reader dependencies를 사용한다. 이번 설계에서 새 `.caelab` 포맷은 도입하지 않는다. `Open document…`는 type-aware chooser와 최근 문서 metadata로 올바른 owner를 연다. 제품 File association 등록은 승인 후 launcher 과제다. `Save portable copy…`는 기존 형식을 담은 **폴더**에 필요한 등록 artifacts와 manifest를 복사·검증하고 새 문서/store ID의 branch로 연다. 원문서 identity를 두 writable store에 복제하지 않는다. 복사 중 오류면 이전 committed folder/원 store 유지, 부분 folder는 incomplete로 표시한다.

### C08. Evaluation·Runner·remote의 정확한 재개 범위

Evaluation은 **이미 있는** kind=`evaluation`과 같은 editor를 독립/Numerical embedded 양쪽에서 연다. 단계 표는1–32 stable stage ID, saved Material/PDE/Simulation ref, operation/port를 사용한다. 전달/반복 값은 같은 owner; 물리 equation/material/solver step은 원 domain editor. 현 exact_same_mesh metadata 요구와 supported scalar binding을 유지한다.

현재 `thermal.fenicsx.rectangle`→`structural.fenicsx.thermoelastic_rectangle`은 지원 SI path다: metre/global rectangular P1 triangular mesh, steady isotropic uniform Dirichlet thermal field, Kelvin nodal capture, plane-stress free expansion/Tref, bounded lagged Picard/restart_safe. **기존 코드 있음; 이번 실행 안 함.** dimensionless general PDE path나 native C3D10 freeze의 thermal metadata를 이 실제 thermal solver의 대체로 쓰지 않는다. K/°C offset, 다른 geometry/mesh/time/field·stateful constitutive 확장은 별도다.

실제 전달 전에는 `Static connection checked / Actual field pending`를 구별한다. 공급 result를 받은 뒤 required receiver locations/times/measure/units 검사→차단 또는 다음 stage 제출. `NOT_CONVERGED`는 job terminal과 별개이며 solver들이 모두 종료해도 유효 목적값으로 채택하지 않는다. history dependent solver의 반복 trial은 물리 step 시작상태로 restore 가능해야 한다; 그렇지 않으면 feedback capability 차단.

현재 prefix reuse는 **whole definition_sha256와 candidate values 동일**, saved domain refs/출발 inputs도 동일해야 한다. 환경 문제만 고치고 같은 정의로 실패 단계부터 새 attempt를 만들 수 있는 경우만 UI에 enabled한다. downstream stage라도 수정하면 definition hash가 바뀌므로 현재 reuse 불가; `Run changed definition`은 새 입력이다. 유연한 영향 기반 prefix reuse는 추후 명시 확장이고 현재 지원이라고 하지 않는다. 반복은 일관된 checkpoint와 adapter restore capability 없으면 중간 단계부터 이어붙이지 않는다.

Runner close와 cancel은 다른 동작이다. `RUN-CANCEL`은 scope(selected attempt / whole Plan / whole Evaluation), no-new-submissions,현재 child·supports_cancel·last observed·terminal observed를 보여준다. 늦은 결과는 original input/attempt에 남기고 search/next stage를 자동 재개하지 않는다. command_id와 job_id는 각각의 status/cancel endpoint를 사용한다. response lost이면 같은 ID 상태부터 읽으며 새 ID 자동 재제출 금지. service restart에서 추적 끊긴 외부 프로세스는 INTERRUPTED+termination unknown; 같은 workdir 재사용 금지.

remote는 기존 file batch export/import의 frozen candidate/exchange/units/failed/missing 검사를 재사용한다. SSH/Slurm/PBS 자동 지원은 이번 source 범위에서 미확인이므로 분리 backlog로 남긴다. 새 host는 alias/transport/allowed root/queue/resource/credential reference만 설정하고 비밀 자체는 프로젝트·로그·시안에 저장하지 않는다. 전송 전 dependency manifest,원격 job token,결과 hash/partial/staging receipt를 유지한다. disconnect는 remote job cancel 성공을 뜻하지 않는다. `Reconnect read status`→same remote ID 확인→명시 fetch 또는 cancel. 실제 scheduler/requeue 정책 없는 경우 history browsing과 exact numerical resume를 구별한다.

### C09. Study·Expert·기기와 현재 결론

Study는 질문·경쟁 가설·support/refute/neutral evidence·명시 판단·다음 연구를 독립적으로 저장한다. 현재 resolver는 saved document/retained result/saved Expert turn ref를 받는다. literature URL을 직접 기존 ref라고 넣지 않는다. 먼저 Data/document/artifact에 원문+locator/hash를 등록하거나, bounded evidence-reference extension을 구현해 확인한다. 링크열만 있는 가짜 근거 완료를 피한다.

Expert provider 미연결/limit에서는 질문·role·논점·사용자 reply 초안과 과거 실제 발언을 열고 저장한다. `Connect eligible provider`는 실제 설치된 허용 경로 확인에 연결; 별도 유료 API fallback 금지. 개발 Pro relay의 인증/구독은 제품 Expert 권한이 아니다. 생성한 Plan은 사용자 편집 후 명시 실행하고 Study 판단은 별도 채택한다. provider 오류/중지 중 solver가 돌고 있다면 각 상태/취소 범위를 따로 둔다.

기기 직접 제어는 파일 기반 교정의 선행이 아니다. 실제 하드웨어/driver/무료 권한/환경·허용 동작이 있을 때 별도 `DEVICE-PLAN` capability로 연결한다. simulation stop, acquisition cancel, physical emergency stop의 의미를 섞지 않는다. 지정된 실제 환경과 승인 없는 장비 작동은 이 시안에서 하지 않는다. 측정/장착/내구 기준이 없으면 UNKNOWN/NOT_RELEASED를 유지한다.
