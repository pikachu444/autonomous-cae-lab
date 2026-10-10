# CAD/FE 전처리·후처리와 독립 연구 작업공간 설계

2026-10-11 제품 기획 합의: [PRODUCT_PLAN](PRODUCT_PLAN.md)은 실제 Pro와 두 차례
기획을 주고받아 확정한 제품 구성·화면 원형·개발 순서와 첫 세 연구 사례의 기준이다.
불량 연구와 제작 전 지그 검토를 모두 포함한다. 아래 기능/명령 계약과 ADR0060을
보존하며 실제 공식 화면과 조작을 구현 기준으로 쓴다. 기존 합성 웹 시안은 보존 자료다.

2026-10-10 경계 교정: **Data, Material Research, PDE Research는 CAD/FE 전처리의 모드가 아니다.** 각 작업공간은 자기 입력 문서·편집·Undo·저장 수명을 소유한다. 공통 프로젝트와 정확한 revision 참조로 연결하며 실행파일 수는 별도 배포 결정이다. 이전의 “비CAD Pre ↔ FreeCAD Pre host 왕복” 제안은 철회한다. 아래 P/V/D 식별자는 추적을 위해 보존하고 소유자를 재배치한다. [ADR0060](../ADR/0060-independent-research-workspaces.md)에 이유·대안·계약 영향을 기록한다. 기존 시안은 이 경계의 구현·수용 증거가 아니다.

2026-10-08 · 상태: **요구·설계 진행 중 · 이전 HTML GUI안 철회 · FreeCAD/ParaView 기반 실제 조작 시안 추가**. 사용자는 실제 FreeCAD 화면의 방향을 수용했지만 제품 전체 완료나 이 문서 전체를 승인하지 않았다. 아래의 요구, 기술 제안, 검증된 좁은 구현을 구별한다. `prepost-workspaces.html`은 구현 지시서로 사용하지 않는다. 실제 관찰과 미실행 항목은 [검증 기록](PREPOST_VERIFICATION.md), 후보·공식 근거는 [재사용 조사](PREPOST_REUSE.md)에 유지한다.

**전체 구현 기준으로 아직 부족한 부분:** 일부 native 선택·메시·결과 명령은 실제 모델로 검증했지만 다중 선택·일괄 편집·메시 진단·곡선/재료점/PDE·통합 문서 관리·조립 운동의 연결 흐름을 모두 검증하지 않았다. 아래 기능/데이터/보존 요구는 유지하고 최종 배치와 제품 계약은 미확정이다. Ouroboros의 질문 종료나 시각화 버튼 동작은 GUI 설계 완료를 뜻하지 않는다.

## 0. 후속 사용자 지시와 이번 시안의 구현 경계

- 사용자가 즉시 실제 시안 제작을 지시했다. 앞선 인터뷰 중 구현 보류는 이 지시로 해제됐다. 이전 HTML 시안의 수용을 뜻하지 않는다.
- Windows 로컬을 WSL 없이 먼저 사용하고 이후 Linux 서버를 연결한다. 기술을 Windows 전용으로 제한하는 뜻은 아니며 웹 기술도 금지하지 않는다. FreeCAD/ParaView native와 Research host를 우선 검증하고, 실제 전문 프로그램의 객체·명령·속성·정보 밀도를 유지한다.
- 기존 오픈 소스와 라이브러리를 적극 사용한다. 사용자가 지정한 [Ponytail](https://github.com/DietrichGebert/ponytail/blob/main/skills/ponytail/SKILL.md)의 재사용 원칙을 적용하되, 요청한 기능이나 검증을 삭제하는 근거로 쓰지 않는다.
- Python 자체를 금지하지 않는다. 대형 CAD/mesh/result의 메모리와 반응성이 중요하다. 이번 15개 표시 부품과 9,155절점 결과는 대형 모델 성능 증거가 아니다.
- 기능이 커질 때 객체의 책임과 설계 패턴을 고려해 구조화한다. 현재의 작은 연결 코드를 제품 전체의 절차적 callback 묶음으로 키우지 않는다.

현재 `apps/desktop_pre`는 원본 사본 열기·native 명령 연결·선택 검사이고, `apps/desktop_post`는 검증된 기존 필드의 native reader 변환·분석 상태·명령·보존 저장이다. FreeCAD의 CAD/GUI와 ParaView의 렌더러/필터/차트/선택기는 upstream 구현이다. 공통 Core/registry/schema는 변경하지 않는다. API 기반 검증, 실제 GUI 클릭, 사용자의 방향 수용, 공학 승인을 별개로 기록한다.

제품 확장 시 책임 경계는 문서/리비전 수명, 편집 명령과 Undo, 화면/선택 바인딩, native backend adapter로 나눈다. 기존 FreeCAD Document/Qt 객체와 ParaView pipeline/proxy를 합성하고, 이미 검증된 공통 스키마를 재사용한다. 복수 backend나 문서 수명 요구가 실제로 생기는 지점에 인터페이스를 두며 지금 사용하지 않는 범용 프레임워크를 만들지 않는다.

무거운 기하·메시·렌더링 계산은 native 구현에 맡긴다. 해시는 스트리밍하고 선택 검사에 전체 형상 복사를 넣지 않는다. 현재 CAD import는 동기 호출이고 post 준비는 전체 필드를 메모리에서 변환하므로 대형 입력의 중단·진행률·메모리 상한은 아직 미검증이다. 규모별 원본 고정 입력에서 열기 시간, 최대 메모리, 선택/회전 반응, 저장·복원, 중단을 측정한 뒤 제품 성능 기준을 정한다.

## 1. 요구의 출처와 해석

| 기준 | 이 명세에서의 효력 |
|---|---|
| 현재 전담 세션 및 후속 지시 | CAD/FE·Post와 독립 연구 도구. Windows 비WSL 로컬 우선, 이후 Linux 서버. 실제 조작·기존 구현 재사용·실제 프로그램 화면 기준. 최신 요구가 과거 가정보다 우선 |
| 원문 `붙여넣은 텍스트.txt`와 [사용자 결정](https://chatgpt.com/space/page_6ac6e6a501508191913070f4ef51eae9), 2026-10-10 경계 지적 | 독립 사용·CAD 없는 연구·외부 ASCII·실제 화면·재사용 유지. 과거 5개 분류에 맞추려고 Data/Material/PDE를 Pre에 넣지 않는다. 논리 책임과 실행파일 수를 구분 |
| [상세 기획](https://chatgpt.com/space/page_6ac6e67d6efc8191af147db299b3cf3b) | 기존 에이전트 초안. 분할·형상 복구·후처리 기능을 검토 대상으로 채택하되 사용자 승인으로 간주하지 않음 |
| [참고·반려 화면](https://chatgpt.com/space/page_6ac6e6ad93388191abe86be695849251) | 객체 선택과 무관한 중앙 곡선, 시연 필드, 형식적인 트리를 교정해야 하는 근거 |
| PROJECT_SCOPE R01–R52, ADR, 현재 코드 | 수치 의미·원본 보존·검증 원칙 재사용. OpenScience 필수, 기존 단일 웹 메뉴 구조는 최신 요구로 대체. 과거 solver 관찰을 새 GUI의 합격으로 재사용하지 않음 |

원본 경로: `C:/Users/pikac/.codex/attachments/8aef385e-5172-48b6-82a4-c59fc1f82bff/붙여넣은 텍스트.txt`.
검토 시작 local `4843c66e482ded31c59604d7cc19d1800be388f4`, origin/main `fc7c82dfcf4a6155ff18b7ebd5b91388916e6a9e`, upstream `3e48bf6138f495299f45b1af254bfb4aaff307b8`. dirty 파일은 건드리지 않는다. 본 세션의 명세·연결 실험은 별도 경로에 추가한다.

## 2. 앱 경계와 첫 전체 구성

### GUI와 MCP가 공유할 명령 계약

사용자는 전문가 에이전트의 도움과 자동 연구를 위해 전처리·후처리의 MCP 제어를 요구했다. 주요 문서·모델·메시·조건·결과 분석 명령을 GUI와 MCP가 같은 서비스/API로 실행하는 것을 제품 요구로 둔다. MCP는 사람이 앱을 실행하기 위한 필수 의존성이 아니다.

현재 저장소의 `openscience/mcp_server.py`에는 native FCStd import/inspect/final 선택, 연구 변수 등록, CAD 실험·해석 실행, 결과 inspect/summary/compare, DOE·최적화가 있다. 기존 Core/registry/immutable experiment 계약을 재사용한다. 이것을 현재 열린 FreeCAD/ParaView 문서의 직접 제어 완료로 해석하지 않는다. 이번 native 시안에는 MCP transport나 live document bridge가 아직 없다.

공유 명령은 명시적 문서 ID·예상 revision·대상 ID·단위·입력을 받고 결과 revision·진단·산출물 참조를 반환해야 한다. 앱 내부 native adapter가 해당 문서에 명령을 적용하고 GUI thread/transaction 규칙을 지킨다. 사용자가 native 편집 중이거나 revision이 달라지면 충돌을 반환하며 미저장 변경을 조용히 덮어쓰지 않는다. 긴 메시·해석은 기존 job 계약의 진행·취소·실패·재접속을 사용한다. 임의 Python 실행을 기본 연구 명령으로 노출하지 않는다.

두 경로를 따로 검증한다. (1) 열린 문서에서 MCP 조회·수정→동일 객체/값의 GUI 반영→Undo 또는 새 revision 저장. (2) 고정 입력으로 무인 전처리→실행→후처리·비교→앱에서 같은 ID/revision과 수치를 다시 열기. 원본 절점과 보간 점, 원본값과 파생량, UNKNOWN 판정을 동일하게 보존한다. 큰 배열은 산출물 참조와 필요한 구간 조회로 전달한다. 전문가 에이전트는 가설·계획·해석을 맡고 수치 후보는 기존 결정적 DOE/최적화 엔진이 만든다.

이 요구는 설계에 반영됐으며 실제 외부 MCP 클라이언트와 두 앱을 연결한 수용 검증은 미실행이다.

| 앱 | 자기 문서/중앙 대상 | 직접 여는 입력 | 소유 출력 | 이 세션의 경계 |
|---|---|---|---|---|
| CAD/FE 전처리 | PrepDocument: CAD·조립·메시·영역·FE 재료 할당·조건·해석 설정 | STEP/FCStd, 지원 mesh, 정확한 재료/이력 참조, 기존 prep | 편집 native CAD, mesh, 지원 FE 입력 snapshot | CAD/FE 상세 명세·좁은 native 시안 |
| Data | DataDocument: 원본·열/축·채널·단위·구간/mask·변환·관측 | CSV/ASCII/text 및 지원 데이터 reader | 재현 가능한 Dataset/Observation revision | P10/P11·V06의 소유자. CAD/solver 불필요 |
| Material Research | MaterialDocument: 구성법칙·계수·초기상태·재료점 driver와 평가 정의 | 법칙/라이브러리, 직접 이력 또는 Data 참조 | 지원 모델의 평가 입력, 모델/계수 revision과 적용 근거 | P12·V13a의 소유자. FE 할당과 구별 |
| PDE Research | PDEDocument: 식/약형식·fields/spaces·domain·BC/IC·계수·이산화·해법 설정 | 수학적 domain, 필요한 경우 가져온/생성된 mesh, 원래 모델 설정 | 지원 PDE 평가 입력과 정확한 domain/mesh 참조 | P13·V13b의 소유자. CAD는 선택 |
| 후처리 | PostDocument: 실제 결과 field/curve, 분석 pipeline, comparison | result manifest, VTU/PVD 등 지원 reader, CSV/ASCII/text | 분석 문서, 원본참조, probe/slice/curve/export | 상세 명세·핵심 실제 조작 |
| 실행기 | Case와 Job/Run | 고정 Case snapshot | immutable Run·원시 결과 | 입출력 계약만 제안; 내부 설계 소유 안 함 |
| 수치 연구 / 최적화 | 변수·평가절차·동정/DOE/최적화/UQ·후보·설계공간 | 각 domain의 평가 입력·관측·response spec | 후보/실행/동정 결과와 원 입력 참조 | 후보 적용은 해당 domain owner로 전달 |
| 전문가 | 대화·근거·제안 | 사용자가 선택한 문서/결과 | 미검증 편집 제안·대화 | 두 앱 실행조건 아님 |
| Workbench | 문서 사이 연결과 갱신 필요 상태 | 저장된 ID/revision·ports | 연결 문서 | 두 앱의 문서 소유·편집·실행을 대신하지 않음 |

두 앱 모두 파일 메뉴와 독립 프로세스·창·문서 수명을 가진다. 각 앱은 Workbench 없이 시작/열기/편집/저장/종료/재개한다. 독립성은 CLI와 URL 개수로 판정하지 않는다. 비AI 작업은 계정·MCP·OpenScience 없이 동작한다. 외부 결과를 열 때 원 solver 설치를 요구하지 않는다.

**재사용과 배포의 기술 제안:** FreeCAD 기반 한 창은 CAD 설계·조립·운동·메시·조건 작업을 담당한다. Data/Material/PDE는 FreeCAD 설치 여부에 따라 host나 문서 소유자가 바뀌지 않는다. 독립 문서 작업공간을 공통 Research 앱에 묶는 방안과 별도 앱으로 배포하는 방안을 비교하되, 직접 열기·작업·저장·재개와 CAD 미설치 사용을 동일하게 요구한다. 논리 작업공간마다 새 exe를 만들거나 하나의 거대 문서로 합치는 것으로 확정하지 않는다. 기존 표·곡선·reader·수치 서비스는 공유한다.

후처리는 ParaView 기반 창에 독립 PostDocument controller와 reader 확장을 둔다. 기존 pipeline·slice·probe·chart·범례 기능을 재사용하고 원 solver 설치를 요구하지 않는다. 화면 기능 전체를 Qt+VTK로 새로 구현하거나 FreeCAD viewport 일부를 옮겨 fullCAD 통합으로 간주하지 않는다. 원본 소스에서 작업대/문서 API와 기능의 존재는 확인했으나, 이 패키지 구조·공유 controller·통합 Undo/저장·첫 설치 후 복원은 **제품 구현 및 실제 검증이 남은 기술 제안**이다. 사용자 승인된 특정 라이브러리 선택으로 기록하지 않는다. 관련 근거와 제한은 PREPOST_REUSE에 연결한다.

### 2.1 독립 Pro 검토에서 보완한 연결 계약

2026-10-11 실제 ChatGPT Pro 검토를 받아 아래 책임을 보완했다. 검토 대상은 기존 두 설계 Page와 공개 기준 명세였으며, 이 로컬 수정본의 코드·GUI·수치 검증을 수행한 것은 아니다. 논리 경계는 이 계약을 따르고 공통 Research shell·실행파일 수는 통합 실험 후 결정한다.

| 경계 | 소유·교환 계약 |
|---|---|
| Data / Post / Numerical | 변환 recipe는 작성 문서 한 곳이 소유하며 입력 revision을 고정한다. Data의 센서/원자료 품질 mask, 연산 결과의 gap/0분모 등 유효성 mask, Numerical Plan의 연구 선택·잔차 정규화·가중치·fit/holdout, Post의 표시/숨김을 구별한다. 표시 변경으로 목적함수를 바꾸거나 단위/시간 변환을 중복 적용하지 않는다. 기존 fitting 선형 보간과 Post exact 기본값은 각각 유지한다. Data 경유는 필수가 아니다. |
| Material / Numerical | Material은 법칙·구현 source/build/version·계수/적용범위·초기상태·driver/protocol·tensor/응력/변형률 규약·적분/substep·접선과 단일 평가를 소유한다. 법칙·계수·protocol은 개별 참조·변경 단위로 둔다. Numerical은 이 정확한 revision 조합, 자유/고정·공유/시험별 변수, 관측–예측 binding, 잔차·가중치·holdout·방법/예산을 소유한다. 이력 수정은 Material 명령 또는 분기로 전달한다. 문서 열기와 의도적인 사용자 확장 코드의 빌드·평가는 별개다. |
| Material / CAD·FE | FE 내부의 단순 재료 정의는 직접 작성할 수 있다. 연구 모델 전달 시 구현 버전·계수·단위·tensor/shear 규약·내부변수/초기화·온도/속도·요소/응력상태 지원을 adapter에서 검사한다. 동정 성공은 FE 호환이나 공학 승인이 아니다. |
| Mesh / PDE | mesh hash 외에 위상/좌표 차원, 단위·frame·변환, tag namespace/차원/의미, 연결 순서·방향·고차 기하, 함수공간/요소 호환과 BC mapping을 보존한다. node/cell/face/적분점/기타 DOF 결과를 구별하고 렌더링 투영은 파생 결과로 표시한다. PDE 자체의 해석적 domain·mesh recipe·적응 메시를 허용하며 run이 만든 새 mesh로 과거 입력을 덮지 않는다. mesh 없는 모델의 확장 여지는 유지하되 구현 완료로 표시하지 않는다. |
| Domain / Runner / Adapter | 물리 모델·step·적분/증분·수렴 허용치·안정화·적응 정책·출력 위치/성분/시점은 domain, 실행 host/queue/workdir·전송·자원·수명은 Runner, deck 문법은 adapter 소유다. 실제 binary/build·library·MPI/thread/GPU/precision은 receipt로 보존한다. 인프라 재시도는 같은 고정 입력의 새 attempt, 수치 정책 변경은 새 입력/Run이다. 원래 선언한 적응 정책의 실행 이력도 기록한다. 외부 deck/include 원본 권한과 GUI 모델 권한을 구별하고 미지원 card를 조용히 재생성·삭제하지 않는다. |
| Study / 복합 평가 / Workbench | 기존 Core Study/Experiment가 질문·모델·시험·비교·근거를 연결한다. 재사용 가능한 복합 평가 정의가 field 전달·mapping·시간 정렬·반복 수렴/중단 조건을 소유하고 Numerical Plan은 탐색을 소유한다. 선택 Workbench는 이 관계의 화면이며 유일한 저장소나 별도 scheduler가 아니다. 출처 DAG와 실행 중 반복은 구별한다. |
| 관측과 실제 시험 | 숫자뿐 아니라 시편·시험 조건·센서 위치/좌표·교정·시간 기준·불확실성을 참조한다. 장비 제어가 미구현이어도 외부 실제 시험을 연구에 연결할 수 있어야 한다. 사진·보고서·원문 위치도 근거로 보존한다. |
| 빠른 평가 / 보존 평가 | 임시 preview는 입력·평가기 식별, campaign은 고정 base+후보 값·state/response/status·실패 원장, 채택·보고·근거용 평가는 정확 입력·필요 원시값·runtime·validity를 보존한다. 이미 보존 요건을 만족하면 고정하며, 부족하면 기록 평가를 새로 수행한다. 매 목적함수 호출을 durable job으로 만들지 않는다. |

후보가 여러 owner의 변수를 바꾸면 owner·base revision·값/단위·candidate 근거를 가진 change-set을 만든다. 각 owner가 새 revision을 준비한 뒤 **필수 변경이 모두 준비된 경우에만 프로젝트의 채택 참조 묶음을 게시**한다. 일부 실패 시 이전 채택 묶음과 미채택 draft를 보존하며 부분 성공을 전체 적용으로 표시하지 않는다. 문서 Undo, 후보 채택 취소, job 취소는 별개이고 분산 Undo를 요구하지 않는다.

기존 혼합 PrepDocument가 있으면 과거 문서/Run을 그대로 읽을 수 있게 유지하고 분리 문서의 원 객체 대응과 이전 근거를 남긴다. 미지원 payload나 부분 실패를 삭제·기본값 치환하지 않으며 과거 Run의 입력 참조를 새 구조로 다시 쓰지 않는다.

## 3. 작업 대상과 선택 규칙 — 화면 배치 미확정

이 절의 좌측/우측 등 위치 표현은 철회한 초안의 기록이다. 작업 대상과 필요한 정보의 관계만 검토 대상으로 유지하며, 위치 표현을 구현 제약으로 사용하지 않는다.

### 전처리

CAD/FE 전처리는 새 CAD/FE 모델과 최근 문서/열기로 시작한다. Data, Material, PDE는 각자의 새 문서/열기 진입점을 가진다. 공통 launcher에서 이들을 고를 수 있어도 Pre의 하위 모드가 되지 않는다. 빈 문서에 예제 곡선이나 가짜 형상을 넣지 않는다. 아래 표의 마지막 세 행은 독립 연구 작업공간이다.

| 작업 화면 | 중앙 대상 | 좌측 트리 | 우측 속성/보조 화면 |
|---|---|---|---|
| CAD 설계 | 실제 스케치/부품과 피처 결과 | 부품→body→sketch/constraints/features/dependencies | 동일 선택 요소·구속·치수·자유도, 피처 task·재계산 진단 |
| 조립·운동 | 실제 부품 인스턴스·관절·추적점 경로 | parts/instances/joints/drivers/traces | 원 부품·인스턴스 구별, 관절축/한계·구동법칙·시간·현재 자세 |
| 모델 준비 | 실제 3D CAD/mesh, 선택·방향·진단 overlay | geometry→assembly/part/body; mesh→sets/quality; named regions; material definitions/assignments; conditions; diagnostics | 선택 object/body/face/node/element의 속성, geometry 작업 task, mesh task, material/condition editor |
| Data (독립) | curve와 원시 표, 선택 구간 | dataset→channels/segments/transforms | 열 매핑·단위·품질/결측·구간·변환. 연구용 weight/holdout는 Numerical Plan에서 참조 |
| Material (독립) | 실제 입력 strain/deformation/temperature history 표·곡선 | material law, coefficients, drivers, internal state, outputs | tensor 규약·시간축·단위·지원 engine |
| PDE (독립) | domain/필요 mesh와 식·약형식 문서 | fields/spaces/coefficient/boundary/initial/equations | 단위·성분·영역 참조·이산화·solver 설정·구문/지원 검사; 임의 코드를 자동 실행하지 않음 |

geometry와 curve를 같은 기본 예제로 묶지 않는다. CAD/FE에서 조건 선택은 적용 영역·방향을, 재료 할당 선택은 body/set과 정의값·할당 목록을 보여준다. CAD/FE 할당 대상이 없을 때 '미할당'으로 표시한다. Material 문서는 법칙·계수·driver/state를, PDE 문서는 식·field·domain/boundary 참조와 진단을 표시하며 body 할당을 요구하지 않는다.

**SelectionContext 제안:** `{document_id, revision, object_id, instance_path, association, entity_ids, selection_source}`. renderer row·표시용 삼각형·native face·FE 요소는 다르며 원 부품과 조립 인스턴스도 구분한다. 클릭/트리/표 중 어느 입력이든 이 컨텍스트 하나를 갱신하고 트리 소유 항목·중앙 강조·속성을 동시에 갱신한다. 선택 ID 조회에 실패하면 이전 객체 속성을 남기지 않는다. 수천 face/node를 트리에 무조건 나열하지 않고 소유 body, 검색, 선택 목록과 이름 있는 집합을 사용한다.

클릭=교체, Ctrl=추가/해제, Esc=현재 선택 해제/진행 task 취소(명확한 현재 단계에만), 바디·면·모서리·절점·요소 필터를 항상 표시한다. 박스 선택은 현재 필터를 따른다. 선택만 보기/숨기기/전체 표시/Fit은 계산 입력을 바꾸지 않는다. hover와 저장된 named selection을 분리한다.

### 후처리

| 작업 화면 | 중앙 대상 | 트리 | 속성/제어 |
|---|---|---|---|
| 필드 | actual mesh/field, 변형은 actual U가 있을 때만 | source→dataset/field catalog; saved selections; derived filters; diagnostics | source/run, association, unit/frame, native IDs, filter params |
| 이력/표 | 시간/위치 curve와 원시 sample table | source→channels, location histories, curves | physical quantity/component, time unit, interpolation/source |
| 비교 | 나란히 실제 결과 또는 curve overlay | baseline/comparison sources, alignment operation | 공통 단위·시간·ID/공간 대응·mismatch 사유 |

field/component/association은 중앙 상단, 시간은 재생바에 둔다. 모든 성분·시간을 트리로 늘리지 않는다. source 변경 시 존재하지 않는 field 선택은 해제하고 사용 가능한 목록을 다시 읽는다. 노드값·요소값·적분점값을 구별한다. 중앙에 단위와 원본/파생 구분, component, time를 표시한다.

이전에 제안한 좌측 260px/우측 320px의 3열 배치는 철회한다. 문서에 폭과 위치를 적어 놓으면 구현자가 해당 구조를 재현할 수 있으므로 완성 GUI 명세로 인계하지 않는다. 모델의 실제 가시 면적, 명령 접근, 개체/선택/속성의 정보 밀도, dock 이동·접기·복원, 키보드 반복 작업을 대표 모델과 결과로 평가한 뒤 배치를 결정한다. 표의 수치 정렬, 표시 반올림과 원본 값의 구별, 색 외의 오류 상태·원인·대상 표시는 유지한다.

### 이전 GUI 구성 제안 — 동작 요구는 검토 유지, 배치는 철회

사용자가 HyperMesh 등 전문 도구와 비교한 화면의 부적절함을 지적했다. 아래 표를 최종 권장 GUI로 취급하지 않는다. 선택 일관성·원본 보존·Undo·복구 등의 기능 요구와 검증 시나리오는 유지하되, 모드 계층과 패널 배치는 다시 설계해야 한다.

| 구성 문제 | 권장 동작 | 이유와 실제 확인 행동 |
|---|---|---|
| 작업 대상과 명령 탐색 | CAD/FE, Data, Material, PDE는 독립 문서 작업공간이다. CAD/FE 안에 설계/조립·운동/메시/재료 할당·조건/검증·내보내기 명령을 둔다 | Data에서 중앙 표·곡선, 채널 트리, 행 진단을 표시한다. CAD 미설치에서 직접 열고 편집한다. 공통 프로젝트 이동은 문서 소유권 이전이 아니다 |
| 자유 왕복과 맥락 보존 | 모드는 순서 강제 마법사가 아니다. 같은 프로젝트·활성 객체·카메라·미저장 변경을 유지하며 필요한 명령만 전환한다 | 메시 검토 중 형상으로 돌아가 수정하고 다시 메시로 와도 편집과 대상이 유지돼야 한다. 미완료 task는 Apply/Cancel/계속 편집을 선택하며 자동 확정/폐기하지 않는다 |
| 중앙 대상 우선 | 실제 객체·유형·선택 요약·속성·진단을 같은 target에 연결 | CAD/FE 조건은 영역/방향, 재료 할당은 body/set, mesh 품질 행은 요소를 강조한다. Data는 원 행/채널, Material은 law/계수/driver/state, PDE는 식/field/domain/boundary를 표시한다. 무관한 곡선이나 예제를 넣지 않는다 |
| 명령 대상과 임시 선택 | 우측 상단의 선택 요약과 진행 명령의 고정 대상 목록을 구분한다. 대상 변경은 '대상 지정' 명령에서 명시적으로 한다 | 면 A에 조건을 입력하다 B를 클릭했다고 적용 대상이 조용히 바뀌지 않는다. 입력 오류 시 값은 남고 committed 문서는 변하지 않으며, 수정→적용→동작명 Undo로 복구된다 |
| 변경 영향의 가시성 | geometry 변경 preview와 적용 후에 mesh/영역/조건/관절의 갱신 필요·참조 유실을 표시한다. 이전 shape/mesh를 볼 때 출처 revision과 이전 상태를 중앙에도 표시한다 | 없는 면의 조건을 정상처럼 표시하지 않는다. 진단 행에서 이전 대상/현재 후보를 열어 재지정하고, 미해결이면 export에서 해당 오류로 이동한다 |
| 메시 개선의 왕복 | 품질표→실제 요소→소유 영역 확인→국부 설정→재생성→전후 품질·조건 대응으로 연결한다. recipe와 생성 mesh를 별도 객체로 둔다 | 불량 ID 선택을 안정적인 CAD 영역 지정으로 자동 간주하지 않는다. 실패/중단 중 이전 메시·로그를 볼 수 있고, 성공 후 새 ID와 참조를 재검증한다 |
| 결과 비교의 맥락 | 각 뷰에 source/filter, revision, association, component, 실제 time, unit을 표시한다. 기본 두 뷰에 A/B/차이를 바꿔 넣고 세 뷰 배치도 제공한다 | 카메라/시간/범례 연결을 개별 설정한다. 가까운 시간의 조용한 대체 금지, mapping 불가/0 분모 이유 표시. 화면 클릭은 계산 task의 고정 A/B를 바꾸지 않는다 |
| 후처리 선택 수명 | 일시 선택은 위치 요약에, '탐침 저장'은 분석 트리에 둔다. 고정 개체 추적과 매 시점 조건 재평가를 구별한다 | 마지막 frame 최대값 개체의 시간 이력과 매 frame 최대값 이력을 혼동하지 않는다. source 전환 후에도 저장 탐침을 보존하고, 없는 frame/field는 gap으로 남긴다 |
| 파일 명령과 재개 | Ctrl+S는 앱의 전체 작업 프로젝트 저장이다. 원시/파생 데이터 내보내기와 native 상태 export는 별도 명령으로 둔다 | native ParaView의 기본 Save Data를 프로젝트 저장으로 오해하지 않게 조정한다. 종료·재열기 뒤 이력·조건 또는 필터·비교를 계속 편집할 수 있어야 한다 |
| 창 크기·키보드 | 좌/우/하단 dock 크기 조절·접기·배치 원복을 제공하고 중앙 작업을 우선한다. 파일/편집/보기 메뉴, 맥락 메뉴, 선택 검색, 공통 단축키를 함께 제공한다 | 1100×760과 큰 창에서 핵심 명령을 잃지 않는다. Esc는 현재 native tool/task가 먼저 처리하고 전역 선택 해제가 중복 실행되지 않는다. 오류색만으로 상태를 전달하지 않는다 |

**대표 연결 흐름:** (a) 형상 면 선택→조건 명령→대상·단위·방향 preview→Apply→조건 트리/중앙 glyph 갱신→Undo→다시 적용→프로젝트 재열기. (b) 품질표의 불량 요소→국부 영역 설정→재메시→조건 참조 진단→복구→고정 입력 내보내기. (c) 두 원 결과 열기→수량·위치·시간 대응→A/B와 차이·변화율 확인→저장 탐침/곡선 추출→분석 프로젝트 재열기. 이 흐름으로 명령 발견·잘못된 대상 방지·오류 복구·재개를 실제 평가한다.

배치 탐색용 파일 `prepost-workspaces.html`은 **철회한 시안의 기록**으로만 남긴다. 구현 화면의 기준이나 GUI 수용 증거로 사용하지 않는다. 실제 CAD·메시·solver·분석 pipeline은 연결되지 않았다.

### 전문 도구와 대조해 보완해야 할 설계

공식 문서를 확인한 비교이며 상용 앱을 이 컴퓨터에서 실행한 검증은 아니다.

| 근거 | 현재 초안의 구체적 부족 | 필요한 설계 산출물 |
|---|---|---|
| [HyperMesh Model Browser](https://2025.help.altair.com/2025/hwdesktop/hwx/topics/user_interface/browser_model_overview_c.htm)는 절점·요소·형상·하중·재료 등 모델 개체의 편집/표시를 지원하며 유형별 속성 열·검색·필터·정렬을 연결한다 | 단순한 트리 버튼과 설명용 속성창으로 다수 개체를 탐색·비교·편집하는 작업을 보여주지 못했다 | 개체 유형/ID/이름/속성 열, 선택 집합, 다중/일괄 편집, 표시/숨김/격리와 명령 대상의 구분을 실제 조작으로 명세 |
| [ANSYS Mechanical Application Interface](https://ansyshelp.ansys.com/public/views/secured/corp/v252/en/wb_sim/ds_Interface.html)는 리본·그래픽 도구·Outline·Details·그래픽 선택·맥락 창·단축키와 형상 갱신 후 참조 복구를 별도 작업으로 다룬다 | 명령군과 선택 필터, 진행 명령의 입력 단계, 편집 중 모델 확인, 재참조의 조작 경로가 충분히 설계되지 않았다 | 동일 모델에서 명령 진입→대상 선택→수치 입력→미리보기→적용/취소→반복·수정하는 화면 상태와 키보드/마우스 동작 |
| 기존 사용자 요구: 메시 개선, 결과 보기, 차이/변화율 비교, 같은 창의 CAD 설계·조립·운동, 저장·재개 | 기능 목록은 있으나 품질 기준/분포/불량 개체 검토와 field/component/association/time/범례/단면/탐침/곡선의 효율적 조작을 실제 데이터로 입증하지 못했다 | 대표 업무별 실제 모델·결과, 정상/오류/복구 화면, 재사용 native 명령 대응표와 실행 가능한 연결 시안 |

기획 완료 판단에는 위 산출물, 재사용 통합 가능성의 실제 근거, 구현 가능한 현재 명세와 남은 제한이 필요하다. 이미 답한 CAD·조립·메시·결과 비교 범위를 다시 사용자에게 결정하게 하지 않는다.

## 4. 공통 문서 상태와 명령 수명

아래 공통 규칙은 5–6절의 **모든** 변경 명령에 적용한다. 개별 명령의 추가 규칙이 있으면 그 규칙을 병기한다.

| 상태/행동 | 정해진 동작 |
|---|---|
| 로딩 | source/진행/취소 표시. 현재 열린 문서는 새 입력 검증 완료까지 유지. 취소·reader 실패는 current document를 교체하지 않음 |
| 편집 preview | 변경 draft와 affected objects 표시. Apply 전 committed revision과 실행 입력은 바뀌지 않음. native task는 working document를 preview transaction으로 변경할 수 있으므로 Cancel/Esc가 geometry·참조·dirty를 함께 rollback해야 함 |
| Apply | 원자적 문서 transaction. 대상·단위·finite/type/backend 지원 재검사; dirty와 undo 항목 생성 |
| Undo/Redo | 편집 내용과 종속 참조/validity를 함께 복원. 과거 solver Run은 삭제·수정하지 않음. renderer 선택 변경은 별도 navigation history이며 물리 undo와 혼합하지 않음 |
| 처리 중 | geometry/mesh/filter 작업의 job token·source revision 고정. 새 편집으로 source가 달라졌으면 늦은 결과를 현재 문서에 적용하지 않음. cancel은 child 종료 확인 후 CANCELLED, 미확인 시 UNCONFIRMED |
| 실패/재시도 | 입력과 로그·원인·마지막 유효 결과 보존. 같은 실패를 자동 반복하지 않음. 사용자가 수정/환경 복구 후 Retry하면 새 attempt ID |
| 미저장 이동/닫기 | Save / Discard local edits / Cancel. Save 실패이면 창 유지; 취소는 이동 안 함. 다른 열려 있는 문서 저장에 영향 없음 |
| 저장 | 문서 baseline revision/hash와 disk 현재값 비교, 원자적 replace/lock, 새 revision과 immutable prior snapshot. source raw는 덮어쓰지 않음 |
| 외부 변경 충돌 | overwrite 금지. '디스크 다시 열기'(local edit 폐기 확인), '별도 사본으로 저장', '차이 보기' 제공. 자동 last-writer-wins 금지 |
| 중단/재개 | 마지막 committed revision + recovery draft를 별도 제시. 진행 중 job을 완료로 복원하지 않음. 재연결은 소유 job receipt가 있을 때만 |
| 누락 source | 같은 basename만으로 재연결하지 않음. Locate에서 source hash/type/revision 확인. 다른 내용이면 새 source로 가져오기 |

저장하는 `view_state`는 camera/panel/active field/range/time/saved analysis 포함. transient hover는 제외한다. camera/range 변경만으로 input fingerprint를 바꾸지 않는다. 분석 파라미터 변경은 post analysis revision을 올리지만 원 Run을 무효화하지 않는다.

## 5. 입력 작업공간 주요 명령 — 기존 ID와 소유자

P01–P09/P14–P20은 CAD/FE, P10/P11은 Data, P12는 Material, P13은 PDE가 소유한다. P14는 FE 검증·내보내기이며 Material/PDE 검증은 각 owner의 독립 평가 계약을 따른다. FE 재료 할당은 versioned law/계수와 지원 adapter를 참조하며 구성모델 연구 문서를 대신 편집하지 않는다. Data 변환과 Post 파생 분석은 공통 reader/연산 서비스를 재사용하되 각 recipe를 만든 문서가 소유한다. 수치 연구의 bounds·목표·시험 분할·후보는 Plan이, 재료법칙/물리 입력은 domain 문서가 소유한다.

| ID / 명령 | 전제 → 조작 | 실제 데이터·화면 변화 | 실패/취소/Undo/재개 특칙 |
|---|---|---|---|
| P01 STEP/native 가져오기 | 지원 reader·원본 파일 → file dialog→units/bodies/bounds/validity preview→Import | 원본 read-only snapshot, editable native document, body tree/viewport 생성; scale 원본/적용값 기록 | unknown unit은 미확정. 취소는 현재 문서 유지. invalid shape는 조사용으로 보존하되 export 차단. Undo는 import transaction 전체 |
| P02 선택·이름 있는 영역 | 현재 revision의 body/face/edge/node/element → filter→pick/box/ID search→이름/멤버 확인→Save region | 실제 membership과 source revision 저장; tree·highlight·properties 연결 | empty/mixed incompatible association 차단. transient selection≠saved region. remesh 이후 direct node/element set은 unresolved |
| P03 이동·회전/치수 | editable object → Placement 또는 exposed parameter→unit/value preview→Apply | native editable operation·bounds 갱신, affected mesh/refs stale | finite/허용범위 오류 차단. Undo geometry+dependency state. arbitrary STEP에 없는 feature parameter를 만들어 표시하지 않음 |
| P04 분할/Boolean/단순화 | 유효 body+plane/tool/feature selection → before/after preview→affected regions→Apply | native shape operation 저장, 새 geometry revision; mesh는 이전 것을 reference-only로 유지 | failed operation은 old shape 유지. old FaceN 자동 재부착 금지. 제거한 face/새 ambiguity는 UNRESOLVED; Undo 시 shape와 bindings 함께 복원 |
| P05 조건 참조 복구 | geometry/mesh 변경 뒤 broken refs → 진단→old target preview와 후보→사용자 재선택→Confirm binding | 새 revision에 old→new mapping·방법·사용자 근거 기록 | nearest face/같은 번호 자동 확정 금지. 중복/없는 후보이면 그대로 미해결, export 막힘. Cancel은 이전 미해결 상태 |
| P06 mesh 생성·국부 개선 | valid shape+supported element/order → global/local size·영역별 분할 설정→preview 영향→Generate | 실제 메시와 사용 설정·대상 geometry revision 저장. node/element count/type/quality 표시. display tessellation과 별도 object. 생성할 때마다 새 mesh revision이며 기존 메시 보존 | 별도 worker/temp output 후 성공 시 채택. failure/cancel은 last valid mesh 보존하되 현재 geometry와 stale 여부 표시. 생성 중 source 변경이면 결과 자동 적용 금지. old mesh Undo는 revision 참조로 복원. 설정 저장·재열기 후 수정하여 새 생성 가능 |
| P07 mesh 품질·개선 반복 | actual mesh → metric definition/backend→quality list/histogram→불량 요소/영역 선택→국부 크기·분할 조정→P06 재생성→전후 품질 확인 | 실제 요소와 원 ID를 중앙에서 강조. 조정 대상 CAD 영역과 이전·새 메시의 raw 품질값 및 설정 차이 표시. 재메시 뒤 조건/집합 참조를 재검증 | inverted/zero Jacobian blocker와 warning 분리. 허용치 근거 없으면 UNKNOWN. 기준을 낮춰 통과시키지 않음. 새 메시 ID를 이전과 동일 대상으로 간주하지 않으며 미해결 참조는 명시적 복구. 직접 절점 이동·요소 삭제/재연결은 현재 단계에서 후속 검토 |
| P08 재료 정의/할당 | chosen law+supported backend → coefficients/units/ranges/origin→body/set targets→Apply | definition과 assignment 별도 객체; 미할당 body 바로가기 | E/nu 등 물리 admissibility는 domain 규칙. assumed material은 assumed. 참조 없는 정의와 실제 할당 구분. Undo 둘을 정확히 되돌림 |
| P09 BC/load/initial/contact | 해석 종류+valid region → kind→target→frame/components/value/history→glyph preview→Apply | condition tree와 실제 영역·방향·값 표시 | 압력 vs 총힘 단위/분배 명시. 혼합 target/겹친 incompatible DOF/empty target/미지원 card 차단. 취소는 glyph draft만 제거 |
| P10 CSV/ASCII 매핑 | data-only empty/기존 문서 → encoding/delimiter/header/column/quantity/unit/time preview→Import | immutable raw+mapping+numeric table/curve. 원시 line/row ID 보존 | malformed row/NaN/duplicate/nonmonotonic axis는 정확한 행과 정책 표시; silent drop/0대체 금지. 규칙 지정 후 재시도 |
| P11 점/구간/처리 | mapped dataset → table/curve select→구간/품질 제외 사유/변환 draft→Apply | raw 보존+derived dataset/recipe. selected row와 marker 연동. 연구 선택·weight/holdout 편집은 참조하는 Numerical Plan 소유 | x/y 단위 불일치·범위 역전 차단; 보간·smooth는 방법/params 별도 파생. Undo·재개 시 구간/원 행 mapping·품질 사유 복원. 표시 숨김과 계산 제외를 구별 |
| P12 재료점 입력 | CAD 없는 새 작업→supported law·계수/단위→driver tensor 규약·time/strain/deformation/temperature/초기상태 편집→Validate | 실제 입력 표·곡선의 원 행 ID 선택 연동, coefficient catalog와 expected output declaration 저장. stress/strain/engineering shear/finite-strain measure 구별 | tensor크기·단위·시간순서·누락값 오류를 해당 셀에 표시. invalid draft 저장 허용, 실행용 export 차단. Cancel/Undo는 이력·규약 함께 복원. 수정 후 재검증. 재열기 후 동일 값/규약/초기상태를 계속 편집. 적분 전 결과 생성 금지 |
| P13 PDE 정의 | CAD 없는 analytic/지원 mesh domain→field/space/coefficient→식/약형식·BC/IC 편집→Validate | 식 원문과 의미 있는 영역·경계·필드 참조 연결, 선택 항의 대상 강조, 구문/rank/unit/operator 지원 진단 | 미정 기호·잘못된 rank/단위·유실 영역을 정확한 식/객체에 표시. 임의 코드를 자동 실행하지 않음. invalid draft 보존, export 차단. Cancel/Undo 후 재검증. 저장·재열기 후 식/계수/영역·경계/오류를 복원해 편집 |
| P14 FE 검증·내보내기 | CAD/FE candidate revision → Validate→blocker jump→backend+format→input summary→Export | 정확한 FE 입력/native/mesh/조건 revision, 지원 adapter와 검증 receipt | invalid parameter/CAD/mesh/unresolved binding/unsupported required term은 block. UNKNOWN engineering requirement 보존, release 승인과 구별. export 자체 solver 시작 안 함. Material/PDE의 독립 평가 입력은 각 owner 계약이며 PrepDocument를 요구하지 않음 |
| P15 스케치 생성·편집 | editable part+기준평면→스케치 모드→지원 선/호/원 생성·수정→완료 | 실제 스케치 중앙, 요소·구속 트리, 같은 요소 ID/좌표/단위 속성. 지지평면과 요소를 native 편집객체로 저장 | 비평면/유실지지참조 진단. Cancel은 이번 draft, Undo는 요소와 관련 구속 함께 복원. 수정 후 재시도. 저장·재열기 후 요소/구속 재편집 |
| P16 구속·치수 풀이 | 스케치 요소→치수/일치/평행/수직/접선 등 지원 구속→단위/값→Apply | 실제 풀이 결과 형상/치수/잔여자유도 갱신, 구속 행과 관련 요소 강조 연동 | 과소구속은 자유도 표시, 임의 구속하지 않음. 모순/중복은 원인과 구속 표시, 마지막 유효 형상 유지. 수정/제거 후 재풀이. Undo/재열기 후 구속·형상·풀이상태 재확인 |
| P17 피처·이력·재계산 | 유효 스케치/shape→지원 돌출/회전/절삭 생성 또는 기존 치수/참조 편집→영향 preview→Apply/Recompute | 편집값과 피처 의존graph 저장. 실제 피처 결과·후속 피처·mesh·조건·관절 참조 상태 갱신 | 불완전 profile/순환/실패피처 진단. 이전 형상은 이전 상태로 표시하고 최신 결과로 채택하지 않음. Cancel draft폐기, Undo 의존상태 함께 복원. 수정 후 재계산. 재열기 후 이력 편집 가능 |
| P18 배치·조립·관절 | 프로젝트 부품/출처확인 참조→instance배치→기준부품 고정→두 좌표계/축→지원 관절·한계 Apply | 원 부품 ID와 instance ID 구분, tree/view/properties에 관절 대상·축·DOF·한계 표시. 같은 프로젝트 dirty에 포함 | 동일instance연결/없는참조/과구속 진단, 마지막 유효배치 유지. 유실참조 자동대체 금지. Cancel/Undo 배치·관절복원, 명시적 재지정 후 재시도. 저장·재열기 후 참조와 설정 계속 편집 |
| P19 관절구동·운동·경로 | 유효 조립/관절→구동법칙·시간범위·표본·추적점/좌표계→계산→재생/step/경로 생성 | 실제 kinematic 계산에 따른 pose·추적점 path/table. 관절·법칙·시간 설정과 계산 프레임/궤적 artifact를 구별해 저장 | 반환상태·유효frame확인 후 성공표시. 한계/특이점/불일치 해당구간 표시, 실패구간을 이어그리지 않음. 설계pose를 preview전에 보존하고 종료/취소/일반저장전에 복원. '현재 자세 적용'만 새geometry revision생성. 설정 수정 후 새attempt. Undo/재열기 후 구동·추적점 복원, retainedpath는 sourcehash검사. 힘/충돌/응력검증으로 확대금지 |
| P20 CAD/FE 모드 전환·재개 | 열린 prep→설계/조립/모델준비→Save→Close→Open | 같은 전처리 창에서 CAD/FE 객체·편집·dirty와 이력·조립설정 복원. 다른 Data/Material/PDE 문서는 정확한 참조로 연결 | 미완료task는 Apply/Cancel/전환취소. 모드전환으로 자동저장·폐기금지. 저장실패/누락/외부충돌 공통규칙적용. 이미지/최종STEP재열기로 이력복원을 대체하지 않음 |

P14의 성공은 '입력 생성 완료'다. 실제 계산의 수치/물리 합격을 뜻하지 않는다. 일반 저장은 invalid draft도 보존할 수 있고, 실행용 export는 invalid draft를 거부한다.

## 6. 후처리 주요 명령

| ID / 명령 | 전제 → 조작 | 실제 데이터·화면 변화 | 실패/취소/Undo/재개 특칙 |
|---|---|---|---|
| Q01 결과/ASCII 가져오기 | independent app → file(s)→reader+arrays/time/units/association preview→Open | actual data catalog/topology/fields/time/source, unsupported arrays 명시 | solver 미설치 허용. absent field 생성 금지. source parse 실패 시 current pipeline 보존; 선택한 reader/line 진단 후 재시도 |
| Q02 field/component/time | available catalog → association→field→component/magnitude→actual time | 값·단위·frame·time·range·view 동시 갱신 | 없는 component 선택 불가. tensor invariant는 명시 규약과 필요 성분이 있을 때 파생. frame outside data는 no data, 최근값 조용히 재사용 금지 |
| Q03 원 절점/요소 선택 | source mesh → point/cell filter→pick 또는 ID table/search | tree owner+3D+row+properties 같은 native ID. row index도 별도 표기 | derived filter ID와 original ID 혼동 금지. original mapping 없는 filter는 original identity unavailable |
| Q04 범례·단위·범위 | dimensional field → compatible display unit→auto/local/global/fixed range→Apply | display conversion only; raw preserved. clipping/out-of-range 표시, fixed range compare에 공유 가능 | incompatible dimensions/log scale≤0 거부. bounds order 검사. view undo에 기록, solver stale 아님 |
| Q05 변형 형상 | source에 실제 displacement vector 있음 → reference/warped toggle→scale→Apply | actual U 기반 geometry 표시와 배율 라벨; stress component와 독립 | U 없음/association mismatch면 기능 비활성. 원래 geometry와 scalar raw 불변 |
| Q06 단면 | topology+available field → plane origin/normal widget or numbers→preview→Apply | stored Slice filter, outline/field, original cell mapping 가능 범위 표시 | zero normal/범위 밖은 invalid 또는 empty slice 안내. filter undo; source 보존; save/reopen parameters 복원 |
| Q07 탐침 | source+association → native node/element pick **또는** XYZ interpolated probe→Save name | ID/좌표/값/time/unit/method/source. saved probe tree와 central marker | native pick과 보간값 명시 구분. data 밖은 invalid/gap. remesh에서 같은 ID를 같은 위치로 취급 금지. 일시 pick은 저장 안 되며 Save probe로 승격 |
| Q08 위치 이력/선상 추출 | saved native/spatial probe+time-series 또는 line endpoints→method/sample count→Apply | curve/table; source time axis·unit·valid mask·mapping 기록 | field 없는 frame은 gap, 0 아님. interpolation 공간/시간 각각 명시. Undo derived filter; 원시 변경 없음 |
| Q09 여러 실행 비교·차이/변화율 | baseline+candidate→quantity/component/units/association/frame/time/topology 대응 확인→side-by-side/overlay/차이·변화율→Apply | 독립 원 source IDs 유지, optional linked camera/range. 차이와 변화율은 별도 derived field/curve로 계산·표시·저장하며 선택 위치에서 원 A/B 값과 계산식을 함께 확인 | 차원이 다른 값·미정 단위·좌표계/association 불일치는 차이 계산 차단. exact sample default. 시간 보간은 방법/공통 유효구간을 명시하며 외삽·결측구간 연결 금지. 다른 mesh는 명시적 mapping 검증 전 field difference block; 나란히 보기는 가능. Cancel/Undo는 이전 분석 복원 |
| Q09a 시간·단위 대응 | 둘 이상의 source→공통 표시단위·시간축 확인→원 표본 비교 또는 명시적 보간 선택 | 원 값·시간축을 유지하고 대응표에 원 시간·변환·exact/interpolated/unmatched 표시. 비교 설정을 분석 revision으로 저장 | 시간 허용오차/보간 정책을 숨기지 않음. 비대응 표본은 gap. 원본은 변환 결과로 덮어쓰지 않음. 저장·재열기 후 동일 source와 정책으로 차이 재현 |
| Q09b mesh·위치 대응 | source별 mesh/association/frame 확인→동일 native entity 증거 또는 명시적 공간 mapping/탐침→미리보기→Apply | source별 원 ID와 비교 위치·좌표변환·공간보간·평균화·유효 mask를 별도 파생 분석으로 기록 | 같은 ID 숫자만으로 위치 일치를 인정하지 않음. mapping 없는 필드차이, 미지원 association 변환 차단. 영역 밖은 gap. 취소/Undo·mapping 수정 후 재시도 가능. 재열기에서 source hash와 대응 재검증 |
| Q10 추출·내보내기 | selected arrays/source/filter/time/association → format/columns/precision/path preview→Export | CSV+metadata sidecar 또는 native output; IDs/coords/time/component/unit/source hash/run/input revision 포함 | raw vs displayed/derived values 선택과 변환 명시. ID를 float 반올림해 잃지 않음. cancel temp 삭제, 과거 export overwrite는 사용자 명시 경로 확인 |
| Q11 분석 저장·재열기 | imported source+analysis pipeline → Save post document→close→open same | source refs/hashes, filters, saved probes, curves, comparison, view restored | PVSM만으로 원 data/units/provenance/일시 선택이 보존된다고 주장 안 함. source missing/changed→수리 화면, 그 전 결과로 가장하지 않음 |

**차이 연산의 기술 명세 초안:** 기준 A, 비교 B를 사용자가 명시적으로 선택한다. 동일한 물리량·성분·좌표계·단위로 대응시킨 뒤 `차이 = B - A`, 기본 상대량은 `기준 절댓값 대비 변화율(%) = 100 × (B - A) / abs(A)`로 이름과 식을 표시한다. 숨겨진 부호 규약이나 0 분모 대체값을 두지 않는다. `A=0`이면 변화율은 undefined와 이유를 기록하고 차이는 그대로 유효할 수 있다. NaN/결측/영역 밖은 mask를 유지하며 0으로 대체하지 않는다. 작은 분모로 큰 변화율이 생기면 A/B 원값을 함께 확인할 수 있고 임의 epsilon으로 누락시키지 않는다. 다른 변화율 규약을 추가하면 별도 명칭/식/버전으로 저장한다. 이 수학 규약은 담당자의 검토 가능한 제안이며 사용자 지정 수치 규약으로 기록하지 않는다. 단위변환·시간/공간 대응·성분 연산 순서, 원 source hash/revision, mapping과 mask를 AnalysisOperation에 남긴다.

## 7. 앱 사이 파일 계약 제안

이 절은 로컬 프로토타입의 manifest 제안이다. Core 공통 schema/registry/API를 여기서 변경하지 않는다. native CAD 경로와 solver syntax는 adapter에 남긴다.

| 객체 | 필수 의미 |
|---|---|
| DocumentIdentity | UUID, owner/domain kind(CAD/FE, Data, Material, PDE, Post 등), schema_version, revision, parent_revision, title, created_by_app/version; 경로·host는 identity가 아님. 이는 UI 문서 개념이며 새 Core wire enum 채택이 아님 |
| SourceRef | source_id, relative URI, role(raw/native/processed), media_type, bytes/hash, origin(imported/simulation/synthetic/measured), producer/version, original filename, retention |
| EntityRef | source/geometry/mesh revision, association(body/face/edge/node/element/gauss/row), native ID(s), local/display index 별도, frame; native ID 없는 raw table은 row ID만 |
| Region | region_id/name, membership/selection recipe, source revision, RESOLVED/UNRESOLVED/STALE, mapping method/evidence; same FaceN은 binding 증거 아님 |
| Channel/Field | quantity, unit/dimension, association, components/convention, coordinate frame, time/axis values+unit, validity/missing reason; source array name 그대로 보존 |
| CaseSnapshot | 해당 domain 입력 revision/fingerprint와 소비하는 source refs, adapter/version·지원 범위·검증 receipt. geometry/mesh/conditions는 실제 필요한 입력만 포함; 실행 관리는 공통 Runner/평가 서비스 |
| ResultRef | immutable run_id/result_id/input snapshot/producer/raw refs/status. imported result는 run unknown 허용; 없는 run provenance를 만들어내지 않음 |
| AnalysisOperation | op_id/type/source refs/parameters/output refs, original vs derived, interpolation/averaging/alignment policy; 작성 Data 또는 Post 문서가 자기 recipe를 소유. Numerical의 잔차/가중치와 ViewState는 별도 |
| ViewState | active object/field/component/time/camera/range/panels; input fingerprint 제외. saved probe와 filter는 analysis state |

문서 bundle은 manifest+immutable assets+history를 상대 경로로 묶는 제품 후보다. native `.FCStd`와 `.pvsm`은 보존하며 bridge manifest가 의미/원본 해시를 보완한다. 실험용 단일 JSON이 제품 bundle 구현 완료라는 뜻이 아니다.

**편집·저장 소유권:** 각 domain DocSession이 자기 문서·draft·Undo·revision을 소유한다. 공통 프로젝트는 이 문서들의 정확한 참조를 저장하며 전체를 한 PrepDocument나 한 Undo queue로 합치지 않는다. CAD/FE 세션 안에서는 native 구속·피처·조립graph를 FCStd로 보존하고 CAD transaction과 조건·mesh·dirty·Undo를 함께 처리한다. 다른 domain의 원본은 참조하며, 변경은 그 owner의 명령으로 새 revision/분기를 만든다. 원본 import/과거snapshot/기존Core experiment는 GUI 수정 대상이 아니다. 세션 간 Undo stack 보존은 요구하지 않지만 재열기 후 편집 이력·의존관계와 추가 편집/Undo는 유지한다.

저장은 해당 owner의 새 revision payload와 실제 사용하는 dependency snapshot/hash를 준비·검증한 뒤 committed manifest를 마지막에 게시한다. CAD/FE는 native 파일과 외부 부품, Post는 분석/native state, Data/Material/PDE는 각 입력·recipe·참조를 저장한다. native 파일은 비CAD 문서의 의무 산출물이 아니다. 하나라도 실패하면 '전체 저장 완료'로 표시하지 않고 이전 committed revision과 dirty/recovery를 보존한다. 각 owner의 Ctrl+S/Save As/Close는 같은 저장 경계를 사용한다. 외부 writer가 기존 Lab lock을 따르지 않을 수 있으므로 baseline/disk hash충돌 검사는 별도로 필요하다. portable 내보내기는 그 문서가 필요로 하는 dependency와 경로mapping 확인 후에만 완료된다. 재열기에서 동일이름이 아닌 정확한 hash/revision/object mapping을 검증한다.

PostDocument도 source manifest·의미 metadata·분석 operation·PVSM을 같은 revision에 저장한다. native Save State는 별도의 상태 export이고 프로젝트 전체 저장과 구별한다. 재열기 후 필터·탐침·차이계산을 다시 수정/Undo/저장할 수 있어야 한다. 기존 adapter의 저장snapshot admission·native_face_catalog revision·request-local verified read·artifact provenance를 재사용하며 현재 Core/registration/append-only 실험계약을 교체하지 않는다. full assembly CAD편집 지원은 기존 fixture single-solid solver지원과 별개다.

| 변경 | 같은 문서 영향 | 다른 앱 영향 |
|---|---|---|
| geometry shape 변경 | geometry revision↑, mesh stale, affected refs unresolved, case invalid | dependent Runner/optimization input '갱신 필요'; 원 Run/Post source 보존, 자동 재실행 없음 |
| remesh | mesh revision↑, direct node/element refs 재검증, CAD regions explicit remap | 새 input 필요; 기존 결과 old mesh로 계속 열림 |
| material/condition/PDE/curve value 변경 | input fingerprint↑, 검증 다시 필요 | 의존 evaluation stale, 기존 Run immutable |
| unit의 의미/scale 수정 | 원 값 의미 변경이면 새 derived data+fingerprint | downstream stale. 표시단위 변환은 이 경우와 구별 |
| camera/range/selection/panel | view state만 변경 | solver/optimizer stale 없음 |
| post slice/probe/alignment 변경 | analysis revision↑ | response selector를 참조한 optimization만 새 response version 필요; 원 Run 불변 |
| source 외부 수정 | hash mismatch, source admission 중지 | 새 source로 등록/검증; 기존 데이터에 조용히 대체하지 않음 |

열기 전달은 `{document_uri,document_id,kind,revision,optional_object_id}`로 정확한 저장본을 요청한다. app mismatch·revision 없음·hash mismatch를 숨기지 않는다. 오래된 revision은 읽기전용 열기와 새 working copy 분기를 구분한다. 문서 작성자는 해당 앱, 결과 작성자는 Runner/import adapter, Workbench는 연결만 소유한다.

## 8. 실제 검증 시나리오와 수용 기준

V01/V07/V08의 독립 열기·저장·재개·충돌 검사는 각 문서 owner에 적용한다. V06은 Data, V13a는 Material, V13b는 PDE 수용이다. 동일 프로젝트에 CAD 참조가 있어도 독립 연구 문서는 CAD host 없이 편집·저장할 수 있어야 한다. 필요한 참조가 없는 특정 평가만 제한한다. native CAD 왕복은 V02/V11/V12이며 비CAD 문서를 FreeCAD로 이동시키는 검증으로 대체하지 않는다.

| Gate | 실제 행동/측정 | 합격 조건/한계 |
|---|---|---|
| V01 독립 창 | Windows에서 Pre/Post 직접 실행, Workbench/AI 없이 새 파일 | 각 창 file workflow 완결. mature tool 실행은 재사용 feasibility이며 제품 완성 아님 |
| V02 CAD 준비 | known dimension STEP import→body/face select→Placement/Boolean/split→Undo→save/reopen | 실제 shape/bounds/volume·editable operation·selection ID 일치. split 미관찰이면 별도 미완료 |
| V03 mesh/조건·개선 반복 | actual mesh 생성→품질표에서 실제 요소 선택→국부 크기/분할 조정→재생성→전후 비교→material/force/fixed 재검증→save/reopen | 원 native counts/IDs/품질과 화면 일치. 설정·대상 영역·조건 복원. 이전 메시 보존, 생성취소/실패 때 현재 결과 유지, 재메시로 직접 ID 참조가 바뀌면 미해결 표시. 허용치를 바꾸지 않고 변화 기록. geometry change 안전 binding 검사는 별도 gate |
| V04 stale/rebind | assigned face가 topology 변경으로 없어짐→export→undo/rebind | 조용히 잘못된 face에 붙지 않음; unresolved가 export 차단; original snapshot 보존 |
| V05 실제 field | 원본 ID 있는 VTU/PVD import→array/time→pick→slice→native/probe 값 | 원 배열과 독립 계산/reader 대조. synthetic reader field는 SYNTHETIC으로 표시, stress로 부르지 않음 |
| V06 외부 curve | CAD/solver/AI 없이 CSV매핑→표/curve선택→구간/품질 제외/파생변환→Undo/Redo→save/reopen→export | 원시값/행ID불변, 구간/처리정책/파생값 재현. malformed입력에서 currentdoc유지. source행과 derived행 연결. Numerical weight와 Post 표시 상태는 별도 |
| V07 저장·재개 | Pre/Post 모두 종료→자기 saved native+manifest 독립재열기→각각 실제편집 하나→저장 | same sourcehash/filters/units/savedprobes, 편집이력·관절 또는 필터/비교 추가편집 가능. 단일물리파일·세션간Undo스택·임시선택 보존을 요구하지 않음 |
| V08 충돌/복구 | same doc 두창 수정→다른 창 저장→현재 저장 | conflict 차단·save-as 또는 reload, 과거 revision 보존. 종료 중 job 완료로 오표시 안 함 |
| V09 화면 | 실제 OS screenshot 전/후+클릭/입력/selection/save/reopen | tree-central-properties 연동, actual values/source, 명령 발견성. offscreen/test count로 대체 금지 |
| V10 계산 증거 | 기존 qualified solver 결과를 source pins와 함께 읽거나 별도 신규 run | solver/version/input/reference/tolerance 별도 기록. GUI·CI·exit0만으로 physics 승인 금지 |
| V11 연결 CAD·운동·재개 | 같은창/프로젝트에서 구속스케치→부품→치수·피처수정→2부품조립·관절→구동·경로→save/close/reopen→다시치수/관절편집 | 실제형상·관절계산·편집이력복원, part/instance/jointID·참조일치. 단순회전관절추적좌표를 독립강체변환기준과 사전고정오차로 대조. 외부CAD창·영상·최종형상만으로 대체불가 |
| V12 CAD실패·Undo·참조 | 모순구속→수정→피처참조변경/삭제→recompute→관절·조건상태→Undo→재지정 | 원인/깨진의존표시, 이전결과최신오표시금지, 유실참조 export차단. Undo형상+종속상태복원. 복구뒤save/reopen. 재생취소/저장으로설계pose복원, 명시Applypose만geometry변경 |
| V13a 재료점 편집·재개 | CAD없는입력tensor/계수/history→잘못된시간·단위→진단→수정/Undo→save/reopen→추가편집 | 규약/단위/행ID/값/초기상태복원, invalidexport차단, 실제적분없는출력생성금지 |
| V13b PDE편집·재개 | CAD없는domain/mesh→field·식/약형식·BC/IC→미정기호/틀린경계→수정/Undo→save/reopen | 식원문과field/domain/boundary참조유지, 정확한오류위치·invalidexport차단, 재열기후편집가능 |
| V14 시간·단위·차이 | 동일선형이력을 다른표본과s/ms·N/kN으로준비→exact→명시선형보간→차이·변화율→0/음수기준·차원오류→save/reopen | 독립변환/보간/표시식기준과 사전고정오차내일치. exact/interpolated구분, domain밖/gap보존, N↔Pa거부, 0기준변화율undefined·차이유효, 원본/정책/출처보존 |
| V15 다른mesh비교 | 다른mesh/ID→mapping없이차이요청→명시위치대응/공간보간→영역밖probe→save/reopen | mapping없는차이차단. 합성affinefield는SYNTHETIC표시후독립식대조, 실제solver검증으로승격금지. 원ID·위치·방법·mask보존. 영역밖값생성금지 |

원 사용자 수용은 어떤 내부 gate로도 대신하지 않는다. 시험용 source/결과는 새로운 run directory에 보존하며 historical experiment를 덮어쓰지 않는다.

V06/V13a/V13b는 입력창 저장 시험으로 끝내지 않는다. CAD·AI·Numerical Plan 없이 Material 단독 실제 평가와 A→B→A 상태 격리, PDE 단독 계산과 독립 기준해/field 오차를 확인한다. 지원 evaluator·실행 OS를 명시하고 기존 benchmark의 허용치를 유지한다. 새 기준 문제는 실행 전에 오차 기준을 고정한다. CAD 없는 Numerical 직접 진입·fit/DOE, Post 외부 결과 직접 열기, 각 owner의 추가 편집·재개도 확인한다. GUI/MCP는 같은 document/entity/base revision·generation·단위·검증 규칙을 사용하고 두 문서 A/B, stale 요청, 재전송, 늦은 응답, 저장 후 재열기를 검사한다. 독립 실행의 Run ID까지 같을 필요는 없고 resolved input·평가기·응답 의미가 같아야 한다.

필수 반례: Post 숨김/범례가 fit 목적함수를 바꾸지 않음; Data 새 revision이 과거 fit 입력을 바꾸지 않음; 끊긴 PDE boundary tag는 실행 차단; 실패 후보가 삭제/0잔차로 바뀌지 않음; solver 없이 문서/지원 결과 재열기; 다중 owner 적용 실패 시 기존 채택 묶음 유지. invalid draft를 연 상태에서 마지막 정상 입력을 몰래 실행하지 않는다. 과거 정상 snapshot 실행은 그 대상을 명시적으로 선택할 때만 허용한다. 새 경계 수용은 현재 모두 NOT_RUN이다.

## 9. 인터뷰와 남은 사용자 선택

Ouroboros interview/seed 스킬을 적용한다. 실제 session/질문/답과 Seed 파일·검사 결과는 검증 기록에 연결한다. 설치·tool listing만 성공했으면 인터뷰 완료라고 쓰지 않는다.

| 쟁점 | 이미 확정된 것 | 남은 판단/계속 가능한 작업 |
|---|---|---|
| 앱 독립성 | CAD/FE·Post의 독립 사용, Data/Material/PDE의 독립 문서와 CAD 없는 진입, 수치 연구·Runner·Expert·선택 Workbench | 독립성 재질문 없음. 기능별 exe 개수와 host 배포는 검토 제안으로 구별 |
| CAD 편집 깊이 | **사용자가 설계까지 포함 선택:** 스케치·구속·피처 이력·부품/조립 설계와 관절 운동·운동 경로·기구 동작 검토까지 전처리 안에서 편집 | 단순 해석 준비 한정안은 미채택. 전체 범위를 명령·검증에 반영해야 하며 STEP 손질만으로 대체하지 않음 |
| 연결 검증 | **사용자 Q4 권장안 수락:** 스케치·피처 수정→두 부품 조립·관절 운동→저장·종료·재열기 후 이력·조립 설정 복원·계속 편집 | 한 논리적 작업/프로젝트의 실제 연결을 검증. 보고서 작성이나 단일 물리 파일 강제가 아님. 이 사례로 전체 제품 범위를 축소하지 않음 |
| 메시 편집 깊이 | **사용자 Q6 "일단 1번":** 국부 요소 크기·분할 설정 조정 후 재생성으로 개선 | 직접 절점 이동·요소 삭제/재연결은 후속 검토이며 영구 제외가 아님. 실제 생성·품질·영역 선택·조건 재검증·설정 저장/재개는 현재 범위 유지 |
| 결과 비교 깊이 | **사용자 Q7 "2번":** 나란히 보기·곡선 겹치기에 더해 차이값·변화율 필드/곡선을 계산·표시·저장 | 비교 가능한 데이터만 계산, 원본·계산 출처 구분. 단위·위치·시간 대응과 undefined 정책을 명시하고 저장·재열기 때 재현 |
| 성숙 앱 재사용 방식 | 적극 재사용. **전처리는 같은 창에서 CAD 모드 전환·문서/미저장 통합 관리로 사용자 확정** | 별도 CAD 앱 왕복은 전처리 목표에서 제외. 2절의 FreeCAD 선택 패키지/ParaView host는 담당자의 기술 제안이며 통합·배포·문서 복원 검증이 남아 있음 |
| 파일 규모·상용 format | 외부 ASCII/CSV/text 반드시, solver 없이 | 요구 파일 예 없으면 작고 공개적인 fixture로 기능만 검증, 대형성능·독점포맷 미완료 |
| 수치/물리 | 원본·invalid metrics·UNKNOWN 보존 | representative prototype를 전 engineering 범위 완료로 승격하지 않음 |

## 10. 후속 구현 작업

| 작업 | 선행조건/소유 경로 제안 | 기대 동작과 완료 기준 |
|---|---|---|
| D01 independent document shell | native CAD/FE·Post controller와 독립 연구 문서 진입점, 기존 공통 저장 서비스 | 직접열기/association/P20/Q11, owner별 dirty·저장/충돌/복구, V01/V07/V08 실제Windows. 비CAD host↔FreeCAD 이전을 요구하지 않음 |
| D02 CAD·조립 bridge | existing fixture adapter+catalog, FreeCAD작업대·transaction·프로젝트명령계층 | P01–05/P15–20, editablegraph+topology/관절참조, V02/V04/V11/V12 실제연결. motion정의와path구별 |
| D03 mesh/conditions | existing adapter/domain admissions, native Gmsh/FEM | P06–09, genuine mesh/IDs/quality/conditions, unsupported card reject, V03 |
| D04 독립 Data/Material/PDE | 기존 `caelab/adapters/file_table.py`, material/PDE 선언·unit/channel·evaluation 계약, owner별 문서 편집기 | P10/P11 Data, P12 Material, P13 PDE의 편집/진단/Undo/재개. V06/V13a/V13b와 실제 평가 연결은 owner별로 판정. CAD 설치로 host가 바뀌지 않음 |
| D05 post readers/pipeline | ParaView/VTK readers + existing retained field/history readers | Q01–08, actual association/time/source ID, saved probe vs hover, V05–07 |
| D06 comparison/exports | existing observation/history comparison·units·원source/association계약 | Q09/a/b/Q10, exactdefault·명시mapping/interpolation·차이/변화율규약·거부조건, V14/V15/재개, 원결과불변·ID정밀도 |
| D07 app contracts | Root-owned proposal review with Runner/optimization/Workbench owners | frozen Case/Result refs, no global redesign, version mismatch/stale/old-result preservation |

본 구현으로 넘어가기 전에 미관찰 gate와 남은 사용자 판단을 명시한다. 기술 검증·화면 검증·사용자 수용을 따로 보고한다.
