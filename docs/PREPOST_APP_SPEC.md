# 전처리와 후처리 앱 요구사항·설계 초안

2026-10-08 · 상태: **요구·설계 진행 중 · 이전 HTML GUI안 철회 · FreeCAD/ParaView 기반 실제 조작 시안 추가**. 사용자는 실제 FreeCAD 화면의 방향을 수용했지만 제품 전체 완료나 이 문서 전체를 승인하지 않았다. 아래의 요구, 기술 제안, 검증된 좁은 구현을 구별한다. `prepost-workspaces.html`은 구현 지시서로 사용하지 않는다. 실제 관찰과 미실행 항목은 [검증 기록](PREPOST_VERIFICATION.md), 후보·공식 근거는 [재사용 조사](PREPOST_REUSE.md)에 유지한다.

**전체 구현 기준으로 아직 부족한 부분:** 일부 native 선택·메시·결과 명령은 실제 모델로 검증했지만 다중 선택·일괄 편집·메시 진단·곡선/재료점/PDE·통합 문서 관리·조립 운동의 연결 흐름을 모두 검증하지 않았다. 아래 기능/데이터/보존 요구는 유지하고 최종 배치와 제품 계약은 미확정이다. Ouroboros의 질문 종료나 시각화 버튼 동작은 GUI 설계 완료를 뜻하지 않는다.

## 0. 후속 사용자 지시와 이번 시안의 구현 경계

- 사용자가 즉시 실제 시안 제작을 지시했다. 앞선 인터뷰 중 구현 보류는 이 지시로 해제됐다. 이전 HTML 시안의 수용을 뜻하지 않는다.
- Windows 데스크톱은 필수가 아니다. 웹으로 구현하더라도 Abaqus/HyperMesh처럼 실제 개체·명령·속성·작업 공간을 조작하는 공학 응용 프로그램이어야 한다.
- 기존 오픈 소스와 라이브러리를 적극 사용한다. 사용자가 지정한 [Ponytail](https://github.com/DietrichGebert/ponytail/blob/main/skills/ponytail/SKILL.md)의 재사용 원칙을 적용하되, 요청한 기능이나 검증을 삭제하는 근거로 쓰지 않는다.
- Python 자체를 금지하지 않는다. 대형 CAD/mesh/result의 메모리와 반응성이 중요하다. 이번 15개 표시 부품과 9,155절점 결과는 대형 모델 성능 증거가 아니다.
- 기능이 커질 때 객체의 책임과 설계 패턴을 고려해 구조화한다. 현재의 작은 연결 코드를 제품 전체의 절차적 callback 묶음으로 키우지 않는다.

현재 `apps/desktop_pre`는 원본 사본 열기·native 명령 연결·선택 검사이고, `apps/desktop_post`는 검증된 기존 필드의 native reader 변환·분석 상태·명령·보존 저장이다. FreeCAD의 CAD/GUI와 ParaView의 렌더러/필터/차트/선택기는 upstream 구현이다. 공통 Core/registry/schema는 변경하지 않는다. API 기반 검증, 실제 GUI 클릭, 사용자의 방향 수용, 공학 승인을 별개로 기록한다.

제품 확장 시 책임 경계는 문서/리비전 수명, 편집 명령과 Undo, 화면/선택 바인딩, native backend adapter로 나눈다. 기존 FreeCAD Document/Qt 객체와 ParaView pipeline/proxy를 합성하고, 이미 검증된 공통 스키마를 재사용한다. 복수 backend나 문서 수명 요구가 실제로 생기는 지점에 인터페이스를 두며 지금 사용하지 않는 범용 프레임워크를 만들지 않는다.

무거운 기하·메시·렌더링 계산은 native 구현에 맡긴다. 해시는 스트리밍하고 선택 검사에 전체 형상 복사를 넣지 않는다. 현재 CAD import는 동기 호출이고 post 준비는 전체 필드를 메모리에서 변환하므로 대형 입력의 중단·진행률·메모리 상한은 아직 미검증이다. 규모별 원본 고정 입력에서 열기 시간, 최대 메모리, 선택/회전 반응, 저장·복원, 중단을 측정한 뒤 제품 성능 기준을 정한다.

## 1. 요구의 출처와 해석

| 기준 | 이 명세에서의 효력 |
|---|---|
| 현재 전담 세션 및 후속 지시 | 전처리·후처리 두 독립 공학 응용 프로그램. Windows 고정 아님. 실제 조작·기존 구현 재사용·하나의 현재 명세. 최신 요구가 과거 가정보다 우선 |
| 원문 `붙여넣은 텍스트.txt`와 [사용자 결정](https://chatgpt.com/space/page_6ac6e6a501508191913070f4ef51eae9) | 5개 독립 앱+Workbench, CAD 없는 작업, 외부 ASCII, 실제 화면, 기존 도구 재사용. 재확인하지 않음 |
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
| 전처리 | PrepDocument: 3D 형상·메시·영역 또는 곡선·구간/재료점/PDE 정의 | STEP/FCStd, 지원 mesh, CSV/ASCII, 기존 prep | 편집 native CAD, prep manifest, mesh, 검증된 Case snapshot | 상세 명세·핵심 실제 조작 |
| 후처리 | PostDocument: 실제 결과 field/curve, 분석 pipeline, comparison | result manifest, VTU/PVD 등 지원 reader, CSV/ASCII/text | 분석 문서, 원본참조, probe/slice/curve/export | 상세 명세·핵심 실제 조작 |
| 실행기 | Case와 Job/Run | 고정 Case snapshot | immutable Run·원시 결과 | 입출력 계약만 제안; 내부 설계 소유 안 함 |
| 최적화 | 변수·평가절차·후보·설계공간 | Case·관측·response spec | 후보/실행 참조 | prep 변수와 post response 위치/단위 연결만 |
| 전문가 | 대화·근거·제안 | 사용자가 선택한 문서/결과 | 미검증 편집 제안·대화 | 두 앱 실행조건 아님 |
| Workbench | 문서 사이 연결과 갱신 필요 상태 | 저장된 ID/revision·ports | 연결 문서 | 두 앱의 문서 소유·편집·실행을 대신하지 않음 |

두 앱 모두 파일 메뉴와 독립 프로세스·창·문서 수명을 가진다. 각 앱은 Workbench 없이 시작/열기/편집/저장/종료/재개한다. 독립성은 CLI와 URL 개수로 판정하지 않는다. 비AI 작업은 계정·MCP·OpenScience 없이 동작한다. 외부 결과를 열 때 원 solver 설치를 요구하지 않는다.

**재사용의 기술 제안:** 전처리는 단일 실행 진입점과 기본 패키지+선택 CAD 패키지로 구성한다. CAD 없는 기본 패키지는 데이터·곡선·재료점·PDE 화면을 제공하며 시작 때 FreeCAD/CadQuery/solver를 초기화하지 않는다. CAD 패키지가 설치되면 앱 시작부터 FreeCAD 기반 창 하나에서 같은 자료 화면과 Sketcher/PartDesign/Assembly/모델 준비 모드를 전환한다. 설치 상태에 따라 launcher가 host를 결정하며 사용자가 기술 제품을 고를 필요는 없다. 실행 중 별도 CAD 창으로 넘기는 방식은 사용하지 않는다. CAD 기능 최초 설치 후에는 저장·복구 가능한 앱 재시작으로 전환한다.

후처리는 ParaView 기반 창에 독립 PostDocument controller와 reader 확장을 둔다. 기존 pipeline·slice·probe·chart·범례 기능을 재사용하고 원 solver 설치를 요구하지 않는다. 화면 기능 전체를 Qt+VTK로 새로 구현하거나 FreeCAD viewport 일부를 옮겨 fullCAD 통합으로 간주하지 않는다. 원본 소스에서 작업대/문서 API와 기능의 존재는 확인했으나, 이 패키지 구조·공유 controller·통합 Undo/저장·첫 설치 후 복원은 **제품 구현 및 실제 검증이 남은 기술 제안**이다. 사용자 승인된 특정 라이브러리 선택으로 기록하지 않는다. 관련 근거와 제한은 PREPOST_REUSE에 연결한다.

## 3. 작업 대상과 선택 규칙 — 화면 배치 미확정

이 절의 좌측/우측 등 위치 표현은 철회한 초안의 기록이다. 작업 대상과 필요한 정보의 관계만 검토 대상으로 유지하며, 위치 표현을 구현 제약으로 사용하지 않는다.

### 전처리

시작 화면은 새 모델, 새 데이터, 새 재료점, 새 PDE와 최근 문서/열기다. 빈 문서에 예제 곡선이나 가짜 형상을 넣지 않는다. 단일 앱 안의 열린 문서 탭은 허용하되 두 앱의 구분을 탭으로 대체하지 않는다.

| 작업 화면 | 중앙 대상 | 좌측 트리 | 우측 속성/보조 화면 |
|---|---|---|---|
| CAD 설계 | 실제 스케치/부품과 피처 결과 | 부품→body→sketch/constraints/features/dependencies | 동일 선택 요소·구속·치수·자유도, 피처 task·재계산 진단 |
| 조립·운동 | 실제 부품 인스턴스·관절·추적점 경로 | parts/instances/joints/drivers/traces | 원 부품·인스턴스 구별, 관절축/한계·구동법칙·시간·현재 자세 |
| 모델 준비 | 실제 3D CAD/mesh, 선택·방향·진단 overlay | geometry→assembly/part/body; mesh→sets/quality; named regions; material definitions/assignments; conditions; diagnostics | 선택 object/body/face/node/element의 속성, geometry 작업 task, mesh task, material/condition editor |
| 실험 데이터 | curve와 원시 표, 선택 구간 | dataset→channels/segments/transforms | 열 매핑·단위·결측 처리·구간 bounds/weight/활성 |
| 재료점 | 실제 입력 strain/deformation/temperature history 표·곡선 | material law, coefficients, drivers, internal state, outputs | tensor 규약·시간축·단위·지원 engine |
| PDE | 영역/mesh와 식·약형식 문서 | fields/spaces/coefficient/boundary/initial/equations | 단위·성분·영역 참조·구문/지원 검사; 임의 코드를 자동 실행하지 않음 |

geometry와 curve를 같은 기본 예제로 묶지 않는다. 조건 선택 시 참조 geometry/region 작업 화면으로 이동하여 적용 영역과 방향을 표시한다. 재료 선택 시 할당된 body를 강조하고 정의값과 할당 목록을 보여준다. 대상이 없으면 '미할당'이며 무관한 curve로 대신하지 않는다.

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
| 작업 대상과 명령 탐색 | 전처리의 상위 작업 대상을 모델/실험 데이터/재료점/PDE로 구분한다. 모델 작업 안에 설계/조립·운동/메시/재료·조건/검증·내보내기 명령 모드를 둔다 | 모든 작업에 CAD 명령을 나열하지 않는다. 데이터로 이동하면 중앙 표·곡선, 채널 트리, 행 진단으로 함께 전환한다. CAD 미설치에서 동일 자료 흐름을 확인한다 |
| 자유 왕복과 맥락 보존 | 모드는 순서 강제 마법사가 아니다. 같은 프로젝트·활성 객체·카메라·미저장 변경을 유지하며 필요한 명령만 전환한다 | 메시 검토 중 형상으로 돌아가 수정하고 다시 메시로 와도 편집과 대상이 유지돼야 한다. 미완료 task는 Apply/Cancel/계속 편집을 선택하며 자동 확정/폐기하지 않는다 |
| 중앙 대상 우선 | 좌측은 실제 객체·유형·표시·상태, 중앙은 실제 선택 대상, 우측은 선택 요약·속성, 하단은 품질/진단/선택표 | 조건을 클릭하면 같은 면과 방향, 재료를 클릭하면 할당 body, 불량 요소 행을 클릭하면 해당 요소를 강조한다. 미할당은 미할당으로 표시하고 무관한 곡선이나 예제를 넣지 않는다 |
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

## 5. 전처리 주요 명령

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
| P11 점/구간/처리 | mapped dataset → table/curve select→범위/weight/exclude/변환 draft→Apply | raw 보존+derived edited dataset/transformation graph. selected row와 marker 연동 | x/y 단위 불일치·범위 역전 차단; 보간·smooth는 방법/params 별도 파생. Undo 원시 복구 가능; 재개는 구간 bounds/원 행 mapping 복원 |
| P12 재료점 입력 | CAD 없는 새 작업→supported law·계수/단위→driver tensor 규약·time/strain/deformation/temperature/초기상태 편집→Validate | 실제 입력 표·곡선의 원 행 ID 선택 연동, coefficient catalog와 expected output declaration 저장. stress/strain/engineering shear/finite-strain measure 구별 | tensor크기·단위·시간순서·누락값 오류를 해당 셀에 표시. invalid draft 저장 허용, 실행용 export 차단. Cancel/Undo는 이력·규약 함께 복원. 수정 후 재검증. 재열기 후 동일 값/규약/초기상태를 계속 편집. 적분 전 결과 생성 금지 |
| P13 PDE 정의 | CAD 없는 analytic/지원 mesh domain→field/space/coefficient→식/약형식·BC/IC 편집→Validate | 식 원문과 의미 있는 영역·경계·필드 참조 연결, 선택 항의 대상 강조, 구문/rank/unit/operator 지원 진단 | 미정 기호·잘못된 rank/단위·유실 영역을 정확한 식/객체에 표시. 임의 코드를 자동 실행하지 않음. invalid draft 보존, export 차단. Cancel/Undo 후 재검증. 저장·재열기 후 식/계수/영역·경계/오류를 복원해 편집 |
| P14 검증·내보내기 | saved candidate revision → Validate→blocker jump→backend+format→input summary→Export | frozen Case with exact prep/geometry/mesh/conditions/version/hash, native deck artifacts | invalid parameter/CAD/mesh/unresolved binding/unsupported required term은 block. UNKNOWN engineering requirement는 보존하며 export 여부는 해당 gate의 정책; release 승인과 다름. export 자체 solver 시작 안 함 |
| P15 스케치 생성·편집 | editable part+기준평면→스케치 모드→지원 선/호/원 생성·수정→완료 | 실제 스케치 중앙, 요소·구속 트리, 같은 요소 ID/좌표/단위 속성. 지지평면과 요소를 native 편집객체로 저장 | 비평면/유실지지참조 진단. Cancel은 이번 draft, Undo는 요소와 관련 구속 함께 복원. 수정 후 재시도. 저장·재열기 후 요소/구속 재편집 |
| P16 구속·치수 풀이 | 스케치 요소→치수/일치/평행/수직/접선 등 지원 구속→단위/값→Apply | 실제 풀이 결과 형상/치수/잔여자유도 갱신, 구속 행과 관련 요소 강조 연동 | 과소구속은 자유도 표시, 임의 구속하지 않음. 모순/중복은 원인과 구속 표시, 마지막 유효 형상 유지. 수정/제거 후 재풀이. Undo/재열기 후 구속·형상·풀이상태 재확인 |
| P17 피처·이력·재계산 | 유효 스케치/shape→지원 돌출/회전/절삭 생성 또는 기존 치수/참조 편집→영향 preview→Apply/Recompute | 편집값과 피처 의존graph 저장. 실제 피처 결과·후속 피처·mesh·조건·관절 참조 상태 갱신 | 불완전 profile/순환/실패피처 진단. 이전 형상은 이전 상태로 표시하고 최신 결과로 채택하지 않음. Cancel draft폐기, Undo 의존상태 함께 복원. 수정 후 재계산. 재열기 후 이력 편집 가능 |
| P18 배치·조립·관절 | 프로젝트 부품/출처확인 참조→instance배치→기준부품 고정→두 좌표계/축→지원 관절·한계 Apply | 원 부품 ID와 instance ID 구분, tree/view/properties에 관절 대상·축·DOF·한계 표시. 같은 프로젝트 dirty에 포함 | 동일instance연결/없는참조/과구속 진단, 마지막 유효배치 유지. 유실참조 자동대체 금지. Cancel/Undo 배치·관절복원, 명시적 재지정 후 재시도. 저장·재열기 후 참조와 설정 계속 편집 |
| P19 관절구동·운동·경로 | 유효 조립/관절→구동법칙·시간범위·표본·추적점/좌표계→계산→재생/step/경로 생성 | 실제 kinematic 계산에 따른 pose·추적점 path/table. 관절·법칙·시간 설정과 계산 프레임/궤적 artifact를 구별해 저장 | 반환상태·유효frame확인 후 성공표시. 한계/특이점/불일치 해당구간 표시, 실패구간을 이어그리지 않음. 설계pose를 preview전에 보존하고 종료/취소/일반저장전에 복원. '현재 자세 적용'만 새geometry revision생성. 설정 수정 후 새attempt. Undo/재열기 후 구동·추적점 복원, retainedpath는 sourcehash검사. 힘/충돌/응력검증으로 확대금지 |
| P20 모드 전환·프로젝트 재개 | 열린 prep→설계/조립/모델준비/자료 모드→Save→Close→Open | 같은 전처리 창/논리프로젝트에서 객체ID·편집·dirty공유. 저장파일/참조상태표시. 편집이력·조립설정·자료를 복원해 추가편집 | 미완료task는 Apply/Cancel/전환취소. 모드전환으로 자동저장·폐기금지. 저장실패/누락/외부충돌 공통규칙적용. 이미지/최종STEP재열기로 이력복원을 대체하지 않음 |

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
| DocumentIdentity | UUID, kind(prep/post), schema_version, revision, parent_revision, title, created_by_app/version; document path는 identity가 아님 |
| SourceRef | source_id, relative URI, role(raw/native/processed), media_type, bytes/hash, origin(imported/simulation/synthetic/measured), producer/version, original filename, retention |
| EntityRef | source/geometry/mesh revision, association(body/face/edge/node/element/gauss/row), native ID(s), local/display index 별도, frame; native ID 없는 raw table은 row ID만 |
| Region | region_id/name, membership/selection recipe, source revision, RESOLVED/UNRESOLVED/STALE, mapping method/evidence; same FaceN은 binding 증거 아님 |
| Channel/Field | quantity, unit/dimension, association, components/convention, coordinate frame, time/axis values+unit, validity/missing reason; source array name 그대로 보존 |
| CaseSnapshot | prep_revision/fingerprint, exact geometry/mesh/conditions/source refs, backend adapter/version, supported requirements and validation receipt; execution owner는 Runner |
| ResultRef | immutable run_id/result_id/input snapshot/producer/raw refs/status. imported result는 run unknown 허용; 없는 run provenance를 만들어내지 않음 |
| AnalysisOperation | op_id/type/source refs/parameters/output refs, original vs derived, interpolation/averaging/alignment policy; post가 소유 |
| ViewState | active object/field/component/time/camera/range/panels; input fingerprint 제외. saved probe와 filter는 analysis state |

문서 bundle은 manifest+immutable assets+history를 상대 경로로 묶는 제품 후보다. native `.FCStd`와 `.pvsm`은 보존하며 bridge manifest가 의미/원본 해시를 보완한다. 실험용 단일 JSON이 제품 bundle 구현 완료라는 뜻이 아니다.

**편집·저장 소유권 제안:** 한 DocSession이 typed prep 상태와 native CAD 작업문서를 소유한다. native 구속·피처·조립graph는 FCStd가 보존하고 manifest는 정확한 native artifact와 typed 조건·자료·출처를 연결한다. 원본 import/과거snapshot/기존Core experiment는 GUI 수정 대상이 아니다. native CAD transaction을 controller가 관찰해 조건·mesh·dirty·Undo를 함께 처리한다. 서로 별개인 CAD/manifest Undo queue를 방치하지 않는다. 세션 간 Undo stack 보존은 요구하지 않지만 재열기 뒤 native 편집 이력과 의존관계가 남아 새 편집/Undo를 수행해야 한다.

저장은 새 revision의 native파일·typedpayload·외부부품 dependency snapshot/hash를 준비·검증한 뒤 committed manifest를 마지막에 게시한다. 하나라도 실패하면 '전체 저장 완료'로 표시하지 않고 이전 committed revision과 dirty/recovery를 보존한다. native Ctrl+S/Save As/Close도 controller의 동일 경계를 사용한다. 외부 CAD writer는 기존 Lab lock을 따르지 않을 수 있으므로 baseline/disk hash충돌 검사는 별도로 필요하다. portable 내보내기는 모든 dependency 확보와 경로mapping 확인 후에만 완료된다. 재열기에서 동일이름이 아닌 정확한 hash/revision/object mapping을 검증한다.

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

| Gate | 실제 행동/측정 | 합격 조건/한계 |
|---|---|---|
| V01 독립 창 | Windows에서 Pre/Post 직접 실행, Workbench/AI 없이 새 파일 | 각 창 file workflow 완결. mature tool 실행은 재사용 feasibility이며 제품 완성 아님 |
| V02 CAD 준비 | known dimension STEP import→body/face select→Placement/Boolean/split→Undo→save/reopen | 실제 shape/bounds/volume·editable operation·selection ID 일치. split 미관찰이면 별도 미완료 |
| V03 mesh/조건·개선 반복 | actual mesh 생성→품질표에서 실제 요소 선택→국부 크기/분할 조정→재생성→전후 비교→material/force/fixed 재검증→save/reopen | 원 native counts/IDs/품질과 화면 일치. 설정·대상 영역·조건 복원. 이전 메시 보존, 생성취소/실패 때 현재 결과 유지, 재메시로 직접 ID 참조가 바뀌면 미해결 표시. 허용치를 바꾸지 않고 변화 기록. geometry change 안전 binding 검사는 별도 gate |
| V04 stale/rebind | assigned face가 topology 변경으로 없어짐→export→undo/rebind | 조용히 잘못된 face에 붙지 않음; unresolved가 export 차단; original snapshot 보존 |
| V05 실제 field | 원본 ID 있는 VTU/PVD import→array/time→pick→slice→native/probe 값 | 원 배열과 독립 계산/reader 대조. synthetic reader field는 SYNTHETIC으로 표시, stress로 부르지 않음 |
| V06 외부 curve | CAD/solver/AI 없이 CSV매핑→표/curve선택→구간/제외/가중치/파생변환→Undo/Redo→save/reopen→export | 원시값/행ID불변, 구간/처리정책/파생값 재현. malformed입력에서 currentdoc유지. source행과 derived행 연결 |
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

## 9. 인터뷰와 남은 사용자 선택

Ouroboros interview/seed 스킬을 적용한다. 실제 session/질문/답과 Seed 파일·검사 결과는 검증 기록에 연결한다. 설치·tool listing만 성공했으면 인터뷰 완료라고 쓰지 않는다.

| 쟁점 | 이미 확정된 것 | 남은 판단/계속 가능한 작업 |
|---|---|---|
| 앱 독립성 | 5 GUI+Workbench, 두 앱 별도, 실제 화면 필수 | 재질문 없음 |
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
| D01 independent document shell | `apps/preprocessor`, `apps/postprocessor`(신규 제안), base/CAD hostadapter와앱별controller | 직접launch/association/P20/Q11, 모드전환dirty유지, dependency저장/충돌/복구, V01/V07/V08 실제Windows |
| D02 CAD·조립 bridge | existing fixture adapter+catalog, FreeCAD작업대·transaction·프로젝트명령계층 | P01–05/P15–20, editablegraph+topology/관절참조, V02/V04/V11/V12 실제연결. motion정의와path구별 |
| D03 mesh/conditions | existing adapter/domain admissions, native Gmsh/FEM | P06–09, genuine mesh/IDs/quality/conditions, unsupported card reject, V03 |
| D04 data-only preparation | remote `caelab/adapters/file_table.py`, 기존material/PDE선언·unit/channel계약 | P10–13편집/진단/Undo/재개, CAD없는V06/V13a/V13b, solver실행과구별 |
| D05 post readers/pipeline | ParaView/VTK readers + existing retained field/history readers | Q01–08, actual association/time/source ID, saved probe vs hover, V05–07 |
| D06 comparison/exports | existing observation/history comparison·units·원source/association계약 | Q09/a/b/Q10, exactdefault·명시mapping/interpolation·차이/변화율규약·거부조건, V14/V15/재개, 원결과불변·ID정밀도 |
| D07 app contracts | Root-owned proposal review with Runner/optimization/Workbench owners | frozen Case/Result refs, no global redesign, version mismatch/stale/old-result preservation |

본 구현으로 넘어가기 전에 미관찰 gate와 남은 사용자 판단을 명시한다. 기술 검증·화면 검증·사용자 수용을 따로 보고한다.
