# FreeCAD·ParaView 프로젝트의 독립 사용·이동·재개 상세 설계

요청 ID: **PRO-NATIVE-PROJECT-20261016-02**

교정 대상: `PRO-NATIVE-PROJECT-20261016-01.md` 전체 대체본

설계일: 2026-10-16
상태: **R1·R2 및 동반 명세 교정을 반영한 구현 계약. 제품 구현·native 수용시험 완료 보고가 아니다.**

## 0. 결정과 범위

**기존 native owner가 저장한 실제 파일 세트를 기존 input registration으로 고정하고, 그 저장본을 가리키는 typed reference와 현지 작업 사본의 위치 바인딩만 추가한다.** FreeCAD의 `Project.save/open`, `.caepre`/FCStd/XLink, ParaView의 `project.json`/PVSM/Workspace/history, 기존 portable 복사·검증·수리와 GUI opener를 재사용한다. 새 Pre/Post 공통 문서 owner, 별도 프로젝트 DB, 서버, scheduler, 모델러, 메시 생성기, solver, 3D viewer는 만들지 않는다.

원 저장본과 현지 편집 대상은 같은 개념이 아니다. 원 저장본의 bytes·물리 입력·과거 결과는 불변이다. 이동을 위한 경로 변경과 현지 owner 식별자 부여는 검증된 파생물에서만 한다. 실제 형상·조건·필터·측정 수정은 새 위치의 기존 native owner에서 수행하고 명시 저장으로 새 native revision을 만든다.

사용자가 끝내는 일은 다음 두 가지다.

- **Pre:** 기존 FreeCAD에서 사용자 조립/FEM을 저장 → 필요한 외부 부품과 연결된 연구를 확인해 사본 작성 → 원 폴더 없이 새 FreeCAD에서 같은 저장 모델 열기 → 선택·치수/조건 편집·Undo·저장 → 다시 복사·다른 process에서 재열기.
- **Post:** 기존 ParaView에서 데이터·pipeline·분석 이력·표시를 저장 → 실제 reader 의존 세트와 보존 분석 결과를 함께 복사 → 원 폴더 없이 새 ParaView에서 선택·카메라·시간·pipeline 복원 → 명시 편집/Apply·Undo·저장 → 다시 복사·다른 process에서 재열기.

독립 앱의 일반 열기·편집·저장에는 Workbench GUI, 연구팀, AI, MCP, 네트워크가 필요 없다. 연구와의 연결에 기존 service/client를 사용할 수 있지만, native-only 사본의 검사·복사·재열기 때문에 Workbench/JobManager를 새로 시작시키지 않는다. Windows native와 현재 설치된 무료 구성요소를 사용한다. 추가 API·계정·구독·크레딧·호스팅·필수 WSL은 없다.

### 0.1 근거와 미확인 경계

이번 교정의 우선 근거는 직접 첨부한 `correction-request(1).md`와 Astra 원문 `REVIEW(1).md`다. 직전 전체 MD의 실제 bytes(132751 bytes, SHA256 `43cf360644da06f63da80264aecf98fdb54963749eedf609ca23b7ee28fe72f7`)를 확인하고 전체 내용을 읽어 교정했다. 종전 요구 `request(20261015-180822).md`와 `source-bundle.md`의 유효 범위는 유지한다.[C-REQUEST][C-REVIEW][R][S]

소스 기준은 `8bd6bd74c2f1932608b1c6c96296216abb6383a5`, fixture pin은 `3e48bf6138f495299f45b1af254bfb4aaff307b8`다. 현재 main `ba8229a71f71ab9a9e76a54158de15dc6a2e7cd5`의 Boolean 기하 검사 교정과 ResearchTeam A/B/C/D·얇은 CLI/MCP 통합 WIP는 **첨부가 직접 보고한 보호 대상**이다. 이번 교정에서 그 main 전체·로컬 WIP·사용자 PC를 다시 조회하거나 실행하지 않았다. §16의 이전 보충 조회 기록은 이전 설계의 근거로만 유지한다.

Data/Material/Numerical/Report/Study/Expert/PDE/Simulation/Evaluation portable의 기존 통합 성과를 되돌리지 않는다. 이번 범위는 CB07/08이며 연구팀 v2 계약과 종료 plugin의 별도 작업을 바꾸거나 대기시키지 않는다. provider·solver·FreeCAD·ParaView·Qt·패키지 설치·Git/Space 쓰기는 수행하지 않았다. 파일 작성 검사는 설계 문서에 대한 것이며 native 수용과 별개다.

### 0.2 교정 결정의 위치

| 교정 | 이번에 고정한 계약 | 주요 절 / 수용례 |
|---|---|---|
| R1 retained 분석을 입력으로 쓰는 B | history별 원 basis와 검증된 reader 슬롯을 graph·bindings 비교에 함께 사용. 현재 cursor 비교와 과거 retained 입력 검증을 구별 | §6.4.1, §7.4–7.5, §11.5 / NP15·25·35·38 |
| R2 과거 저장본 동시 열기 | 두 intent 모두 원 source와 분리된 live ID. saved import의 첫 Save는 같은 live ID의 새 local target만 발행 | §3.3, §5.4, §7.2, §11.1–11.6 / NP26·27·39 |
| 등록 replacement | public `replacements=()` 한 곳, N0 검증 후 private `_replacements`로만 전달 | §4.3, §11.2·11.4–11.6, §15.8 / NP40 |
| Pre 초기 identity·Undo | 새 working 문서의 owner attach 전 metadata-only 초기화. `_transaction`·recompute·사용자 Undo로 원 ID 복귀 금지 | §5.1·5.4, §15.4 / NP41 |
| 부분 history 저장·연구 링크 | 선언된 누락 history 보존 저장과 strict DeclaredResearchLink union. 순수 native `[]` 유효, 원 job은 HISTORY_ONLY | §3.5, §7.4, §8.6·9.1, §11 / NP42·43 |

이 표는 별도 부록 패치가 아니다. 아래 본문·자료형·함수·메뉴·완료 조건이 이 결정을 반영한 전체 명세다. 미리 구현한 Sol 전용 모듈의 이름/재사용 방향은 유지하며 R1·R2 분기만 이 계약으로 맞춘다.

## 1. 재사용 판단과 반드시 닫을 빈틈

### 1.1 기존 코드에 이미 있는 것

| 접점 | 실제 제공하는 기능 | 이번에 다시 만들지 않을 것 |
|---|---|---|
| `apps/desktop_pre/projects.py::Project.save` | GUI thread에서 설계 자세 복원, 연결 문서 수집, native saveCopy, XLink relocation, immutable retained `.caepre` 선발행, 사용자 저장 경로 발행, generation/graph 재검사 | FCStd 직렬화, 조립·FEM 모델, 새 저장 엔진 |
| `native_cad.inspect_project/unpack_project/working_copy/relocate` | archive 구성·멤버 hash·XLink 검사, 검증된 working copy, XLink `file` 속성만 변경 | geometry 재작성·STEP로 대체·문서 이름 기반 추정 |
| `native_inputs._register_set` 및 `Workbench.native_input/input_path` | 원 세트 복사·stat/fstat·재해시·receipt, 등록된 파일만 reader에 전달 | 새 파일 저장소·경로 문자열을 신뢰하는 opener |
| Post `Owner.save_project`, `external.save_project` | pending native property 차단, Workspace prepare, PVSM·source/reader pins·active selection·이력 보존 | Save State를 또 구현하거나 native 출력 엔진 교체 |
| `Workspace._retained_reader_binding/_retained_dependencies/_verify_record` | 실제 reader 이름/type/ordered inputs, 정확한 history revision, retained values 확인 | 현재 editor cursor로 과거 분석 입력 추정 |
| `source_repair.repair_source/partial_state` | 동일 내용 위치 복구, healthy branch 유지, 원 PVSM에서 만든 부분 상태, retained 분석 재개 경계 | 이름이 같은 파일로 자동 대체·전체 pipeline 재계산 |
| `portable_project.inspect_copy/create_copy/verify_project/open_project` | 명시 saved/ack 선택, original archive·typed projection·stage/publication·cold 검증 | 새 전체 portable 프레임워크 |
| `NativeCommands`, native `GuiDispatch` | 현재 owner/session/generation/명령·완료·유실응답 경계 | native 프로젝트 scheduler |

근거: [S-PRE], [S-CAD], [S-INPUT], [S-POST], [S-REPAIR], [S-PORT], [A-CMD].

### 1.2 Codex의 제안 중 수정하는 판단

**첫째, live descriptor는 저장본 증거가 아니다.** `Project.graph_version()`에는 `id(doc)`가 있고, Post descriptor에는 session-global proxy ID와 현재 보고 상태가 있다. `connection_graph.build_graph`도 native 노드의 `exact_reference=None`을 명시한다. 이를 hash해 저장 참조로 바꾸지 않는다. 실제 registration의 원 파일·saved manifest·의존 closure에 결속한다.[S-PRE][S-GRAPH]

**둘째, Post의 PVSM 해시만으로 saved revision 전체를 대표하지 않는다.** 현재 `Owner.saved_revision`은 `workspace_sha256`다. 같은 PVSM 아래에서도 project metadata, history, result files 또는 source declaration이 달라질 수 있다. 기존 필드는 native 상태 표시로 유지하고, 이동용 `snapshot_sha256`는 이 전체 저장 세트를 별도로 식별한다. 새 native owner는 필요 없다.[S-POST]

**셋째, 현재 PVSM 등록·열기가 이미 완성됐다고 쓰지 않는다.** 첨부의 `NATIVE_EXTENSIONS`에는 `.pvsm`이 없고, `post.source_add/repair`는 VTU/PVD 및 정해진 VTT만 받는다. PVSM을 `native_result`로 위장해 `admit_result`에 넘길 수 없다. 같은 `inputs/<D>/input.json`에 좁은 형제 kind **`native_post_project`**를 추가한다. 이 kind는 reader 열기가 아니라 저장 분석 열기로만 라우팅한다.[S-INPUT][S-WB]

**넷째, 현재 dependency walker는 전체 Post closure를 보증하지 않는다.** `external.save_project`는 알려진 `READERS` 외 입력을 `[entry]`로만 기록하고, `_retained_reader_binding`은 XML의 `file` 속성만 순회한다. 병렬 VTK XML의 `Piece@Source`를 놓칠 수 있다. 등록·저장·검증·수리가 동일한 작은 format codec을 소비하도록 정한다. 단순 확장자 허용이나 walker 중복 작성으로 해결하지 않는다.[S-POST][S-WORK][W-VTK]

**다섯째, 경로 이동을 내용 변경으로 오인하는 해시와 물리 identity를 분리한다.** retained 분석을 입력으로 쓴 history는 graph보다 앞선 `bindings` 비교에도 원 FileName이 남으므로 두 비교를 함께 교정한다.[C-REVIEW] 원 container/PVSM bytes 해시는 유지한다. 파생 container의 경로만 변했으면 파생 해시는 별도로 계산한다. `content_set`에 파생 bytes를 넣고 ‘원본과 동일’이라고 통과시키지 않는다. native result의 행·수치·단위·측도·time/part/group·block 순서는 이동 대상이 아니다.

**여섯째, native 추가는 `SUPPORTED`에 pre/post를 넣는 변경이 아니다.** 현재 portable의 연구 owner 열기·saved revision 구조를 native에 강요하면 실패한다. native 선택과 결과 manifest는 별도 명시 branch로 처리하고, 실제 열기는 native opener로 보낸다. 연구 `documents` 배열에 가짜 P/D owner 문서를 만들지 않는다.[S-PORT][A-WB]

## 2. 사용자에게 보이는 전체 흐름

### 2.1 FreeCAD에서 시작하는 작업

1. 사용자는 FreeCAD native Model/Property/Tasks에서 실제 문서를 편집한다. `파일 → 프로젝트 저장`/관리 문서의 기존 Ctrl+S는 `Project.save`를 그대로 호출한다. native FCStd 사본 내보내기는 별도 명령이다.
2. `파일 → 작업 사본 만들기…`를 누르면 현재 모델과 저장 시각, 포함 외부 부품, 선택된 연구/결과가 표시된다. 저장 후 편집이 있으면 **현재 내용 저장 후 포함 / 마지막 저장본만 / 취소**를 고른다. native task의 미적용 입력은 자동 Apply하지 않는다.
3. 현재 내용을 선택한 경우 원 owner가 정상 저장한 뒤 그 완료 결과를 등록한다. 저장 중 취소·실패하면 복사 단계에 진입하지 않는다. 마지막 저장본을 고르면 그 exact revision만 사용하며 현재 화면은 그대로 남는다.
4. 포함 목록에서 필수 외부 Link 문서는 빼지 못한다. 필요 없는 연결 연구는 제외할 수 있다. 누락/버전 다름/미지원 외부 파일 참조는 행별로 표시하고 `위치 찾기` 또는 `저장본 확인`을 제공한다.
5. 새/빈 목적지에 발행한 뒤 `사본 폴더 열기`, `사본에서 모델 열기`를 제공한다. 후자는 현재 FreeCAD 문서를 교체하지 않는다.
6. 원 폴더를 사용할 수 없는 새 위치에서 저장본 검증 → working copy → 실제 `App.openDocument` → 새 local owner attach를 수행한다. object 이름/외부 occurrence/선택을 검증한다. 다른 열린 문서의 이름 충돌이 있으면 새 FreeCAD process를 사용한다.
7. 치수·조립조건 또는 FEM 조건을 실제로 편집하고 Undo/Redo한다. 메시 재생성·solver는 별도의 기존 명시 실행이다. 저장하면 현지 native revision과 사본의 현재 저장 포인터가 함께 확정된다.
8. 다시 `작업 사본 만들기`를 하면 최초 원본과 현지 새 저장본, 현재 선택 연구 관계를 포함한다. 두 번째 cold process에서 원 PC와 첫 사본을 모두 사용할 수 없어도 같은 모델을 열 수 있어야 한다.

실행 중인 solver가 immutable frozen 입력만 읽고 있어도 native 저장을 일괄 금지하지 않는다. 반면 저장 대상 문서/mesh를 현재 native 작업이 변경 중이면 현재 내용 저장을 막고 마지막 저장본 선택을 제공한다. 진행 결과 파일을 완성 결과처럼 복사하지 않는다.

### 2.2 ParaView에서 시작하는 작업

1. 사용자는 native `File → Open`으로 결과를 읽고 pipeline·field/component·time·camera를 조작한다. 관리 분석 저장은 기존 `CAE 프로젝트 저장`을 호출한다. native Save Data/Save State/Save Screenshot은 그대로 별도 기능이다.
2. 이미 저장한 `project.json`이 있으면 그것과 exact PVSM, source pins, native reader inputs, 전체 분석 history/result_files를 대상으로 한다. PVSM만 있으면 `분석 프로젝트로 저장…`에서 현재 지원 reader의 세트를 명시 확인하고 기존 저장 경로로 관리 분석을 만든다. 임의 `.py` state는 자동 실행하지 않는다.
3. `작업 사본 만들기…`에서 결과 A/B, 시계열 frame 수, 보존 분석, 표시 상태, 누락 branch가 읽기 쉬운 이름으로 나온다. native pending properties는 사용자가 Apply/Reset하거나 마지막 저장본을 선택한다. 복사 버튼이 Reset/Apply하지 않는다.
4. 복사·검증은 ParaView pipeline을 평가하지 않는다. 저장된 files와 XML 참조만 검사한다. Post의 source와 retained analysis 파일 모두 포함되기 전 ‘모두 포함’으로 표시하지 않는다.
5. 새 위치에서 원본 PVSM은 보존하고, exact reader registration/type/property/index에만 현지 경로를 넣은 파생 PVSM·project를 만든다. 기존 startup → `commands.restore_workspace` → `external.restore_workspace` → `LoadState` → Workspace 복원 순서를 사용한다.
6. 원문서가 완전하면 저장한 reader·pipeline·view/layout·field/component·시간·camera를 복원한다. source 하나가 없으면 명시 부분 열기로 healthy branch와 검증된 retained 결과를 읽는다. 원 저장본과 누락 정보는 삭제하지 않는다.
7. 사용자는 `위치 다시 연결…`로 동일 내용의 새 등록 세트를 고른다. 내용이 바뀌면 위치 수리가 아니라 `새 결과로 추가`한다. 비교/탐침을 다시 계산하려면 기존 Validate/Apply를 명시 수행한다.
8. 편집·Undo/Redo·저장 후 재복사한다. 첫 사본과 원 source를 차단한 두 번째 process에서 현재 분석과 과거 history를 읽고 다시 편집할 수 있어야 한다.

### 2.3 연구 앱에서 같은 대상을 여는 방법

Study/Expert/Report의 native 근거에는 **그때 저장한 모델/분석 열기**와 **현재 작업 사본 열기**를 구별한다. 전자는 참조된 snapshot, 후자는 사용자가 선택한 local target의 현재 head다. 기본 근거 열기는 전자다. 두 intent의 새 materialization은 모두 독립 live owner ID를 사용한다. 원 dirty 창을 activate해 과거 근거 열기를 대신하지 않는다.

과거 저장본 창에서는 열어 온 source 개정과 `현지 저장 전`을 함께 표시한다. 편집은 가능하며 첫 `프로젝트 저장`에서 **새 작업 사본으로 저장 / 취소**를 고른다. 새 local target에만 저장하고 원 head는 갱신하지 않는다. 취소하면 그 창의 편집은 그대로 남는다. 같은 열기 command의 유실응답은 같은 새 창을 재확인하며, 다른 사용자의 원 창·선택·Undo에는 접근하지 않는다. 세 창(원 창·과거 저장본 import·현지 working target)의 저장은 각각 분리된다.

Numerical/Simulation의 frozen 실행 입력과 editable native project는 별개다. 새 native 참조는 원 모델로 돌아갈 수 있게 할 뿐 이미 제출한 `data_id`, 입력 hash, result hash를 바꾸지 않는다. 현지 편집 후 새 계산은 기존 freeze/registration/실행 승인 경로를 다시 통과한다. imported Post에는 run provenance가 없을 수 있으며 `UNKNOWN`을 허용한다. 없는 run을 만들어 연결하지 않는다.

## 3. 세 층의 identity: 원본·현지 등록·live owner

### 3.1 엄격한 저장 참조 두 개

새 wire form은 다음 두 가지이며 선택 kind 외 필드는 동일하다. 경로, PID, session, token, 실행 허가, native proxy ID는 포함하지 않는다.

```json
{
  "kind": "native_pre",
  "version": 1,
  "document_id": "PSource01",
  "saved_revision": "RSource01",
  "input_id": "DRegistered01",
  "snapshot_sha256": "<64 lowercase hex>"
}
```

```json
{
  "kind": "native_post",
  "version": 1,
  "document_id": "DPostSource01",
  "saved_revision": "R<saved-basis-sha256>",
  "input_id": "DRegistered02",
  "snapshot_sha256": "<64 lowercase hex>"
}
```

값 예시는 실제 ID/해시가 아니다. 위 key 집합을 고정하고 예상치 못한 key는 거절한다. `document_id`는 native 문서 identity, `input_id`는 등록 세트 identity다. 둘 다 D로 시작해도 동일 namespace가 아니다. resolver는 반드시 `kind`를 먼저 검사한다. Pre/Post identity는 문자열 prefix로 추정하지 않는다.

- **관리 Pre:** `.caepre` manifest의 `document_id/revision`을 사용하고 embedded Lab metadata의 document_id와 일치해야 한다. 충돌을 title로 보정하지 않는다.
- **raw FCStd:** 원 파일에 신뢰할 Lab identity가 없으면 명시 등록 때 source binding용 P ID를 부여한다. `identity_origin=registration_assigned`이며 원 FCStd를 수정하거나 과거 native 저장 이력이 있었다고 만들지 않는다. 재사용은 같은 등록 세트에서만 하고 비슷한 geometry를 합치지 않는다.
- **Post:** 기존 `workspace_sha256`는 `native_revision`으로 보존한다. 이동용 `saved_revision`은 아래 `saved_basis`의 canonical hash에 R을 붙인 값이다. 기존 Owner.saved_revision의 의미를 바꾸지 않는다.
- **raw FCStd의 saved_revision:** 관리 revision이 없으므로 동일한 `saved_basis` 규칙을 쓰고 `revision_origin=registered_snapshot`으로 명시한다.

`saved_basis = {native_kind, source_document_id, format, entry_member, source_manifest_pin, members, edges, reader_bindings, declared_native_metadata_pins}`다. members는 아래 logical member·bytes·hash·role의 정렬 목록이며, edges와 reader inputs는 순서를 보존한다. 원 absolute path 및 timestamp는 원 manifest bytes 안에는 남지만 identity 계산을 위해 source 경로를 새 경로로 덮어쓰지 않는다. `input_id`, 현지 filesystem path, transport 정보는 saved_basis에 포함하지 않는다. 검증된 copy/relocation에서는 기존 source identity를 그대로 가져온다. 독립적으로 같은 파일을 다시 등록했을 때 bytes가 같다는 이유만으로 다른 문서 identity를 합치지 않는다. 원 source identity가 없는 raw FCStd의 새 반입은 별개의 등록 identity가 될 수 있다.

### 3.2 `NativeSnapshotRecord`: 기존 input receipt에 결속하는 저장 세트

추가 sidecar `native-project.json`은 등록 폴더에 한 개만 둔다. 새 일반 document owner가 아니라 기존 input receipt가 검증할 manifest다. `input.json.native_project`에는 `{version:1, manifest_file, manifest_sha256}`만 둔다. `manifest_file`은 해당 `inputs/<id>` 내부 상대 경로이고 크기·해시를 검증한다. 원 native metadata의 64 KiB 제한을 큰 closure 목록으로 우회하지 않는다.

```text
NativeSnapshotRecord
  version: 1
  native_kind: pre | post
  input_kind: native_design | native_post_project
  format: caepre | fcstd | post-project | pvsm
  source_document_id: checked identity
  saved_revision: checked identity
  native_revision: original revision/string/null
  identity_origin: native_manifest | embedded_metadata | registration_assigned
  revision_origin: native_save | registered_snapshot
  entry_member: MemberID
  source_manifest_pin: {member_id, bytes, sha256} | null
  members: Member[]
  edges: DependencyEdge[]
  reader_bindings: ReaderBinding[]                 # Pre에서는 []
  native_metadata_bindings: DeclaredMetadataBinding[]
  logical_origins: [{member_id, original_location}] # 원 경로는 증거일 뿐 읽기 경로 아님
  unavailable: MissingDependency[]
  source_links: DeclaredResearchLink[]              # §3.5; 순수 native는 []
  relocation_bases: PostHistoryBasis[]              # §6.4.1; Pre는 []
  history_availability: HistoryAvailability[]       # §7.4; Pre는 []
  producer: {application:freecad|paraview, version:string|null,
             origin:trusted_save|saved_metadata|unknown}
  required_capabilities: [codec/reader/feature identifiers]
  validation: {closure: COMPLETE | DECLARED_PARTIAL, issues: Issue[]}
  snapshot_sha256: H(record without this field)
```

새 writer는 relocation_bases/history_availability를 명시한다. 기존 native sidecar에 이 두 필드가 없으면 **원 key 집합으로 hash를 먼저 검증**한 뒤 read view에서만 [] 기본값을 쓴다. 원 sidecar를 덧써 hash를 바꾸지 않는다. 이동 비교에 필요한 history basis가 없을 때는 source에 들어 있는 실제 증거로 §6.4.1을 검증할 수 있어야 하며 빈 배열을 경로 검증 면제로 쓰지 않는다.

`Member`는 아래 두 구조 중 하나만 허용한다. `id`는 해당 snapshot 안에서 유일한 논리 ID다.

```text
FileMember = {id, storage:"file", relative, role, bytes, sha256}
ArchiveMember = {id, storage:"archive_member", archive_member_of,
                 archive_member, role, bytes, sha256}
```

FileMember.relative는 입력 등록 `files[].relative`와 일치하는 안전한 POSIX 상대 경로다. ArchiveMember.archive_member_of는 이 snapshot의 FileMember ID이며 archive_member는 `.caepre` 내부의 정확한 안전 멤버명이다. 중첩 일반 archive 탐색은 하지 않는다. 내부 FCStd의 Document.xml/XLink 검사는 native_cad가 담당한다. 같은 물리 archive를 외부 파일과 내부 멤버로 두 번 전송량에 합산하지 않는다. 복사 bytes 한도는 FileMember 합계, 압축 해제 한도는 archive의 실제 expanded bytes를 별도로 검사한다. role은 `pre_archive/pre_document/post_manifest/pvsm/source_container/source_data/analysis_data/analysis_container/declared_metadata/research_job_record/research_input_record/research_result_record/research_output` 중 하나다. 뒤의 네 role은 §3.5에서 명시한 파일만 허용한다. root 제한과 검사한 bytes/해시는 archive 내부에도 동일하게 적용한다.

`DependencyEdge={parent_member, locator, child_member|null, required, original_reference}`다. locator는 §6의 format별 고정 구조이며 임의 XPath가 아니다. 같은 child를 여러 occurrence/frame/reader가 참조하면 file은 한 번 저장해도 edge는 각각 남긴다. graph node 해시에 child 해시를 재귀 포함하지 않으며 유한 node/edge table로 표현한다.

`.caepre`의 내부 `documents/*.FCStd`는 이미 저장 시 relocation된 bytes다. `native_copy_sha256`만 있는 저장 전 `source-*.FCStd`를 복원했다고 주장하지 않는다. 이번 copy에서 보존할 원본은 실제 선택한 `.caepre`의 bytes와 그 실제 archive 멤버다.

### 3.3 원 저장 참조와 현지 작업 target을 분리한다

```text
NativeTarget (portable manifest의 native_projects[] 또는 명시 첫 저장으로 발행된 local target)
  target_id: K...
  native_kind: pre | post
  source: NativeSavedRef
  working_document_id: 이 target의 독립 P... 또는 D...
  head_file: native/<target_id>/head.json
  title: 표시용 문자열
  source_lineage: 원 저장 참조/이전 copy의 연결
```

`head.json={version,target_id,working_document_id,head_generation,layer,reference,parent_reference}`는 native 저장본 포인터일 뿐 draft·runs·Undo·실행 상태를 소유하지 않는다. copy가 만든 초기 target은 `DERIVED_BASE`로 원 reference를 가리킨다. 실제 native 저장·등록 뒤에만 `NATIVE_SAVED`와 새 reference를 CAS 발행한다. source reference와 live ID는 서로 다른 namespace의 증거이며 source 문서와 같은 ID로 두 번째 owner를 등록하지 않는다.

**materialization 정책은 두 intent 모두 독립 ID다.**

| intent | source proof | 새로 열 때 live ID / target | 저장 전 상태 |
|---|---|---|---|
| `working` | 검증한 target의 exact expected head.reference | target.working_document_id; target_id 필수 | DERIVED_BASE이면 현지 저장 전. NATIVE_SAVED이면 그 target의 실제 저장 이력 복원 |
| `saved` | 요청한 NativeSavedRef 그 자체; 최신 head를 따라가지 않음 | open_id에 한 번 배정한 독립 owner_document_id; target_id는 null | `UNSAVED_IMPORT`. source는 저장 증거지만 이 local branch의 저장 완료가 아님 |

`OpenBinding.owner_document_id`가 실제 native Owner ID의 유일한 입력이다. Pre의 owner_id_map도 이 open ticket에 고정한다. saved/DERIVED_BASE에서는 새 local child ID를 발급하고, NATIVE_SAVED working에서는 그 target에 이미 저장된 child ID를 검증해 복원한다. 다른 live owner와 충돌하면 takeover하지 않고 열기를 차단한다. 같은 target 재사용은 새 materialization보다 먼저 판단한다. working에서는 target의 ID, saved에서는 새 import ID다. 한 창의 등록 후에는 ID가 바뀌지 않는다. source_document_id는 source proof와 `portable_origin`에만 남기며 NativeCommands duplicate-owner guard와 session의 문서 ID 집합 불변을 유지한다. 같은 source의 child를 공유하는 occurrence는 같은 materialization 안에서만 동일 child ID로 대응한다.

**saved import의 첫 저장은 새 target만 만든다.** 최초 Save dialog의 취소는 target 생성·native Save·head 갱신 모두 0이다. 확인하면 N0 `prepare_target_save`가 새 K와 save_command_id를 기존 local action receipt에 예약한다. 새 K의 working_document_id는 **이미 열려 있는 import의 owner_document_id**다. 다른 기존 target을 고르거나 원 target을 덮어쓰는 분기는 없다. 현재 native 파일/reader는 옮기지 않고 새 native 저장 root만 `native/<K>/saved`로 지정한다.

N1/N2가 기존 native Save를 수행하고, N0가 같은 완료 witness로 등록한 뒤 `publish_head(expected_head=None)`으로 그 K의 첫 head를 발행한다. 첫 head는 바로 `NATIVE_SAVED`; `parent_reference`와 target.source는 원 exact source다. 예약만 있는 K는 정상 target 목록에 노출하지 않는다. 이미 예약한 K/head와 다른 command가 충돌하면 덮지 않는다. native 저장 성공 후 등록/head 실패는 `NATIVE_SAVED_UNPUBLISHED`로 남기고 **등록/발행만 재시도**한다. 이 상태에서 다른 Save가 새 K를 추가 예약하지 않으며 먼저 해당 발행을 확인한다. 그동안 편집된 내용은 dirty로 유지하고 오래된 witness의 generation을 현재 generation으로 올려 깨끗한 상태로 만들지 않는다. 같은 Save 응답 유실로 native 저장을 반복하지 않는다.

head 발행 후 `owner.native_target`에 해당 K를 결속한다. 이는 위치·target 관계의 갱신이며 owner/session ID 교체가 아니다. 이후 Save는 그 K의 expected head CAS만 갱신한다. `OpenBinding`의 원 source/open intent/relocation proof는 그대로다. 닫기 전 Cancel이나 저장 실패는 현재 편집과 이전 확정 저장본을 보존한다. 미승격 import의 복사는 `현재 내용 새 작업 사본으로 저장 후 포함 / 원 저장본만 / 취소`로 구별한다.

**창 재사용 규칙.** working 요청은 같은 target·expected head·working ID·확인된 session·canonical working 위치의 기존 owner만 activate할 수 있다. 이때 dirty 내용은 사용자가 요청한 '현재 작업'이므로 유지하고 표시한다. saved의 **서로 다른 command는 새 materialization**을 만든다. 동일 saved command의 재확인은 기존 open_id/owner만 반환한다. 그 창이 이미 편집됐으면 `현재 변경 있음`으로 알려줄 뿐 exact source 상태라고 재표시하거나 재로드하지 않는다. 원 dirty 창/다른 target을 닫기·병합·identity 변경하지 않는다.

기존 portable manifest는 불변이다. 새 local target은 기존 `native/<K>/head.json` 발행과 현재 native descriptor의 target 연결로 선택하며, 다음 copy에서 명시 선택한 새 saved reference/target을 새 manifest에 포함한다. 최초 manifest를 수정하거나 별도 target DB를 만들지 않는다.

### 3.4 transient 값

`NativeOwnerStamp={document_id,kind,session_id,generation,view_generation,saved_revision,graph_version}`는 **현재 native save/open command의 CAS 값**이다. graph_version은 현재 process에서만 유효하다. pointer 또는 reference의 portable identity로 사용하지 않는다.

`VerifiedNativeInput`, `OpenBinding`, `NativeTargetSaveBinding`, `CompletedSaveWitness`, `ApprovedRoots`, `VerifiedReplacementMap`, `VerifiedHistorySlots`, `NativeOpenTicket`은 service/local adapter가 검증해 만드는 Python 객체 또는 private payload다. 외부 caller가 dict에 같은 key를 적었다고 권한이 생기지 않는다. 공개 API에는 root ID·등록 ID·typed reference·명시 command ID만 받는다.

### 3.5 `DeclaredResearchLink`: 명시한 native/연구/과거 결과 관계만

N0의 `native_project_contract.py`에서 다음 **strict union 하나**를 정의한다. Pre metadata와 Post project의 optional `native_links[]`, 그리고 등록 sidecar의 `source_links[]`가 같은 형식을 사용한다. 없는 필드는 `[]`로 읽고 순수 native 프로젝트에 연구 연결을 요구하지 않는다. unknown native metadata는 원문 보존하되 링크로 추정하지 않는다.

```text
DeclaredResearchLink = {
  version:1,
  relation: native_source | research_context | result_source | recorded_job,
  source: NativeLinkSite,
  target: ExactLinkTarget | JobHistoryTarget,
  authority: HISTORY_ONLY
}
NativeLinkSite = {kind:project}
  | {kind:pre_object, document_member:MemberID, object_name:str}
  | {kind:post_source, source_ref:str}
  | {kind:post_history, object_ref:str, revision_id:str}
ExactLinkTarget = {
  kind:exact, form:exact|result|native_pre|native_post, reference:dict
}
JobHistoryTarget = {
  kind:job_history, job_id:str, operation:str, state_when_recorded:str,
  origin:dict|null,
  records:{job:MemberID|null, submitted_input:MemberID|null, result:MemberID|null},
  output_members:MemberID[]
}
```

모든 표시된 key는 필수이고 추가 key는 거절한다. 식별자 검사는 기존 `check_id`, object/source 이름은 해당 native manifest의 실제 항목에 대조한다. source는 **자기 snapshot 내부 위치**이므로 자기 snapshot hash/reference를 다시 넣지 않는다. self hash 순환이 없다. native_pre/post reference는 §3.1, result는 기존 `TypedReference(form='result')` resolver의 exact retained reference, exact는 기존 saved-document/source resolver가 반환한 **exact_reference 원객체**를 그대로 사용한다. 새로 비슷한 reference schema를 만들거나 missing 키를 채우지 않는다.

N0 `validate_declared_links`는 wrapper와 relation을 검사한다. `native_source`는 native_pre/post, `result_source`는 result, `research_context`는 기존 exact saved reference, `recorded_job`는 JobHistoryTarget만 받는다. 등록의 trusted `bind_declared_links`는 각각 기존 native/연구 resolver로 읽은 exact_reference와 일치 검증한다. mutable/ack-only/current/latest 선택은 exact 관계로 저장하지 않는다. 해당 기존 form의 validator가 제공하지 않는 reference는 `LINK_UNSUPPORTED`이며 임의로 다른 form으로 fallback하지 않는다.

JobHistoryTarget은 이미 선택·기록된 job에 대한 **그때의 기록**이다. 원 `metadata.links`의 명시 job/operation/origin/state와 선택된 파일 pin에서만 생성한다. 완성 기록이 없는 READY/RUNNING/실패도 원 상태 그대로 보존할 수 있고 records의 null은 '원파일 미보존'이다. null을 새 job JSON으로 채우거나 성공으로 바꾸지 않는다. records/output_members는 snapshot의 명시 FileMember 또는 허용 ArchiveMember만 가리킨다. 각 record·제출 입력·결과·출력 bytes를 원 hash와 함께 보존하며 미선택 job 디렉터리·로그·환경파일은 수집하지 않는다. `state_when_recorded`는 과거 상태이지 현재 실행 상태가 아니다.

연결 모드에서 **사용자가 선택한 job ID 한 개**의 실제 record를 최초 기록할 때만 기존 `DesktopLinks.job_record`/정확한 retained owner를 사용한다. 이미 원본에 저장된 link를 재등록·복사·cold 읽을 때에는 원 controller를 조회하지 않는다. 순수 native의 미보존 job 파일은 그대로 없음이다. 현재 동명의 job, parent_project, 최근 run, 전체 store를 탐색해 채우는 동작은 금지한다.

`HISTORY_ONLY`는 실행/harvest/retry/원 session 복원 권한을 부여하지 않는다는 뜻이다. ExactLinkTarget의 정상 source 탐색은 현재 read 권한으로 가능하다. 원 native 파일·원 link bytes는 불변이며 local 탐색에는 검증된 mapping의 별도 projection을 사용한다. `JobHistoryTarget.origin/records`를 현지 실행 origin으로 재작성하지 않는다. 원 source가 없으면 읽기 불가/원파일 미보존을 표시하고 일반 native 편집·저장을 막지 않는다. [C-REQUEST]

## 4. 저장본 등록과 복사 계약

### 4.1 등록은 explicit 쓰기, inspect는 읽기다

저장된 파일의 등록과 portable inspect를 분리한다. `inspect_copy`가 저장·native 명령·registration을 몰래 실행하지 않는다. 사용자가 native 저장 또는 기존 파일 반입을 명시한 직후 registration을 수행하고, 이후 복사는 immutable registered bytes만 읽는다.

등록 입력은 두 가지다.

```text
SavedCommandSource = {mode: completed_native_save, command_id: C...}
SavedFileSource    = {mode: selected_file, native_kind: pre|post,
                      root_id: approved root id, relative: selected relative path}
```

첫 번째는 NativeCommands의 **실제 SUCCEEDED/COMPLETED 결과**와 owner 종류·save operation·generation·retained output을 서비스가 재조회한다. 호출자가 보낸 path/receipt는 받지 않는다. 이미 닫힌 owner라도 검증 가능한 완료 저장 bytes는 등록할 수 있다. `pre.project.save/document.save`가 성공했는지와 **사용자 경로 발행까지 성공했는지**를 구분한다. retained만 남은 실패는 `복구한 저장본 포함`이라는 별도 명시 선택이다.

두 번째는 승인 root/파일 chooser에서 선택된 `.caepre`, `.FCStd`, Post `project.json` 또는 `.pvsm`이다. standalone adapter는 native 파일 chooser에서 명시한 root만 사용한다. 회사 폴더 전체·상위 드라이브·다른 열린 문서를 자동 승인하지 않는다. 연결 모드에서는 기존 `local_roots/local_inputs/register_local_input`과 현재 service root 정책을 사용한다.

`native_design`은 기존 `register_native_input/_register_set`을 사용한다. `native_post_project`는 동일 `_register_set`과 검증된 closure를 사용한다. Post 프로젝트 전체를 일반 JSON 단일 파일 업로드나 `native_result`로 처리하지 않는다.

### 4.2 등록 transaction

1. 원 saved manifest를 제한된 크기로 읽고 before fingerprint를 기록한다. format codec으로 참조와 멤버를 열거한다. macro/script/native pipeline은 실행하지 않는다.
2. root·regular file·logical/resolved path·file limit를 검사한다. 여러 승인 root에 나뉜 파일은 아래 explicit mapping을 사용한다.
3. 기존 `_register_set`의 before stat/fstat·stream hash·size·마지막 전체 stat/hash 재검사를 그대로 사용한다. parsed container bytes의 해시도 복사본과 같아야 한다.
4. 각 member를 등록 staging에 복사한 뒤 **복사된 metadata/container를 다시 parse**하여 edges/children가 snapshot 선언과 일치하는지 검사한다. source 목록이 맞는 것만으로 완료하지 않는다.
5. NativeSnapshotRecord와 sidecar pin을 작성한다. `input.json`은 모든 파일·sidecar 검증이 끝난 후 마지막에 atomic publish한다. 실패 staging을 정상 `inputs()` 결과에 표시하지 않는다.
6. 같은 등록 command를 재확인하면 같은 input ID/ref를 반환한다. source bytes가 바뀌었으면 원 command 재사용은 충돌이다. 검증 가능한 중간 bytes는 보존하고 native Save를 다시 호출하지 않는다.

### 4.3 root와 외부 의존 파일

기본값은 현재 단일 approved root 정책이다. 다른 승인 root의 파일은 사용자가 이전 edge와 **이미 등록된 새 입력 세트**를 명시 대응할 때만 허용한다. public 전달 위치는 `register_saved(context, source, *, replacements=(), command_id)`와 Workbench/Client의 동명 `replacements=()` keyword **한 곳**이다. SavedCommandSource/SavedFileSource 안에는 replacements/receipt/path를 추가하지 않는다. 정규화한 source+replacements 전체를 command signature에 넣는다. 같은 command의 대응 변경은 충돌이다.

N0가 §11.1 RegisteredReplacement를 기존 등록 input/명시 member와 대조해 `VerifiedReplacementMap`을 만든 뒤, Pre `pre_snapshot_files(..., _replacements=...)`와 Post `post_project_files(..., _replacements=...)` → `inspect_dataset`에만 private로 전달한다. 실제 file locator·verified pins/edge map은 이 객체 안에만 있다. caller가 같은 이름의 dict를 보내도 private 검증 객체로 받지 않는다. parent directory/전체 drive를 root로 확대하지 않는다.

대응은 basename이 아니라 `(parent_member, typed locator, expected child pin)`으로 한다. `.FCStd`의 원 absolute XLink가 source PC에서만 해석 가능하면 처음 그 PC에서 등록하거나 이미 보존된 exact child 세트를 사용한다. Linux에서 Windows drive 경로를 상대 파일로 오인해 탐색하지 않는다.

junction/symlink/reparse 탈출은 현재 no_links/root 검사로 거절한다. 정상적인 `..` XLink가 승인 root 안을 가리키는 원 FCStd는 기존 `logical_file` 의미로 판정하되, 생성하는 archive member에는 `..`를 넣지 않는다. PVD/VTK container의 상대 child는 아래 좁은 codec 규칙을 유지한다. Windows 대소문자 충돌, ADS/예약 이름, 경로 길이 초과는 발행 전 표시한다. 파일을 이름 바꾸어 숨겨 통과시키지 않는다.

### 4.4 dirty/미저장/계산 중 정책

| 상태 | 현재 내용 포함 | 마지막 저장본 포함 |
|---|---|---|
| current native 내용이 저장본과 같음 | 추가 Save 없이 exact 등록본 선택 | 허용 |
| geometry/pipeline/view 변경 | 명시 기존 Save가 성공한 뒤 새 registration | 명시 경고 후 기존 saved ref |
| FreeCAD Tasks/edit 또는 Post unchecked properties | native Apply/Cancel/Reset은 사용자 동작. 현재 내용 저장 차단 | 기존 saved ref는 가능 |
| unsaved linked child | 실제 `Project.save`가 그 live child까지 saveCopy한 coherent snapshot만 허용 | parent의 원 saved dependency만 사용 |
| native mesh/설계 자세 변경 중 | `before_design_action`/현재 busy 검사로 차단 | immutable saved ref 가능 |
| 외부 solver 진행 중 | native source와 독립이면 저장 가능. 성장 중 결과는 새 포함 불가 | 기존 frozen 입력/완료 결과만 포함 |
| 사용자 선택 경로 Save 실패 | 전체 저장/복사 성공 아님. retained recovery만 별도 선택 | 이전 정상 saved ref 가능 |
| owner 종료/교체 | live stamp 재사용 금지 | 검증된 disk registration은 읽기·복사 가능 |

native에 일반 acknowledged-memory 직렬화를 새로 만들지 않는다. `draft_policy=acknowledged`는 연구 owner에서 기존처럼 유지하지만 native current를 포함하려면 실제 native 저장 관문을 통과해야 한다. native invalid draft는 기존 `.caepre`/Workspace 저장 정책을 유지하고, 실행 가능 또는 완전 closure와 구분한다.

## 5. Pre adapter: 원 native 저장을 그대로 사용한다

### 5.1 저장 → 검증 → 등록

`Project.save`의 GUI thread 제약, `in_save`, `before_design_action`, linked owner의 같은 검사, native Tasks 검사, generation/graph 확인, short-path saveCopy, binary BREP 선택 범위, retained archive 선발행을 유지한다. 이번 adapter가 shape export, remesh, `recompute()` 또는 운동 계산을 추가하지 않는다. **import identity 초기화는 기존 `Owner._transaction`을 호출하지 않는다.** 이 함수의 recompute는 사용자 편집 transaction의 종전 의미로 남기고, 새 working identity는 §5.4의 attach 전 metadata-only 초기화로 완료한다.[C-REVIEW]

저장 관문에 추가하는 것은 세 가지다.

1. **완료 저장 witness:** 실제 성공한 manifest identity·retained_project·published path의 pin을 반환한다. command outcome이 없으면 live descriptor의 last_save 문자열만으로 SUCCEEDED를 만들지 않는다.
2. **선택적 saved UI 선택:** `project.json`의 optional `native_selection`에 doc member/object/subelement/occurrence chain을 저장한다. native selection API에서 읽은 값만 사용한다. 선택의 값이 geometry 입력 hash에 섞이지 않으며 저장 전후 모델 변경으로 셀/면을 추측 재선택하지 않는다. 과거 파일에 이 필드가 없으면 `선택 기록 없음`으로 연다.
3. **현지 target의 저장 포인터:** 실제 native 저장과 registration이 끝난 뒤에만 `head.json` CAS를 갱신한다. 실패한 경우 native 저장본 자체는 보존하고 `연결 기록 갱신 필요`로 표시한다.

`Project.save`의 native saveCopy 전 파일명·Doc.Name·Link target·선택된 다른 문서가 유지되는지 native 시험으로 확인한다. `exact_shape_serialization`의 parameter 복구를 제거하거나 범위를 확대하지 않는다. 저장 전 BREP preimage가 없는 경우 물리동등성을 새로 증명했다고 쓰지 않는다.

### 5.2 raw FCStd/XLink와 `.caepre`의 처리 차이

**`.caepre`:** `inspect_project` → registered archive bytes 검증 → `unpack_project`를 기본으로 한다. 이미 relative XLink가 닫힌 archive를 다시 평탄화/이름 변경하지 않는다. manifest의 `unavailable_dependencies`는 해결된 것으로 바꾸지 않는다. declared missing replacement가 실제 호스트의 우연한 파일로 해석되지 않도록 working-copy 안에만 결속한다.

**raw FCStd:** `dependency_files`와 registration file set으로 원 graph를 고정하고 `working_copy(registered=..., original_locations=...)`를 사용한다. `original_locations`는 이미 등록된 edge를 source file에 대응하는 용도다. 새 PC에서 옛 absolute path를 실제로 열거나 디렉터리를 검색하는 용도가 아니다. `working_copy`가 `logical_file`로 원 경로를 해석하는 기존 경계는 **검증된 logical origin→member map**으로 제한한다.

동일 basename의 다른 FCStd를 자동 병합하지 않는다. 기존 working_copy의 `_index` suffix만으로 cross-document expression 의미가 보존됐다고 볼 수 없다. 관리 `.caepre`의 실제 native document 이름 대응이 확정된 경우를 우선하고, raw import의 이름 충돌/외부 expression binding이 불명확하면 `FreeCAD에서 함께 열어 프로젝트 저장`으로 coherent `.caepre`를 만든다. 이때 파일 내용을 직접 수정해 식을 재작성하는 구현을 추가하지 않는다.[A-CAD]

동일 child의 여러 Link occurrence는 정상이다. file-level cycle은 무한 순회하지 않고 별도 진단한다. native 저장이 허용한 원본과 invalid draft를 파괴하지 않지만, 이번 v1에서 검증되지 않은 cyclic load를 `COMPLETE_EDITABLE`로 수용하지 않는다. dataset/analysis의 실제 순환 dependency는 차단한다. 단순 재방문과 cycle은 DFS의 visited/active-stack으로 구별한다.

### 5.3 XLink relocation의 허용 변경

locator는 다음과 같다.

```text
{codec: freecad_xlink_v1,
 document_member: MemberID,
 object_name: 원 Object@name,
 property_name: 원 Property@name,
 xlink_index: 정수,
 target_name: 원 XLink@name,
 original_file: 원 XLink@file}
```

`native_cad.relocate`에 주는 resolver는 이 locator 전체와 원 parent pin이 일치할 때만 새 `file`을 반환한다. `target_name`, subelement, occurrence, Placement, shape, mesh, load/constraint, expression, Label은 이 함수에서 바꾸지 않는다.

검증은 XML의 의미상 비교에서 **허용된 정확한 XLink `file` 슬롯만 마스킹**한 구조가 동일한지와 나머지 ZIP entry의 uncompressed bytes/hash가 같은지를 확인한다. XML serializer 때문에 `Document.xml` bytes가 달라질 수 있는 사실을 숨기지 않는다. 원 archive bytes는 여전히 byte-for-byte로 보존한다.

### 5.4 두 intent의 owner 초기화·Undo와 첫 저장

`Project.open(receipt, _portable_binding=...)`의 entry/dependency 검증·`App.openDocument`·`remember_open`·새 owner attach를 재사용한다. 원 owner.doc 포인터를 바꾸지 않는다. 새 process/working 파일은 source와 별개지만 **그 사실만으로 ID가 분리되지는 않으므로** §3.3 OpenBinding.owner_document_id를 attach 전에 적용한다. saved와 working에 동일하다.[C-REVIEW]

`initialize_import_identity(doc, binding, *, member_id)`는 해당 open이 **새로 연 working 문서**에서만 한 번 실행한다. source file/member pin 및 XLink 허용 diff를 먼저 검증하고, 아직 owner observer·broker·사용자 편집 transaction이 없는 상태인지 확인한다. 기존 `metadata.read/write`를 사용하되 `Owner._transaction`, `doc.recompute()`, saveCopy, geometry/mesh/운동 계산은 호출하지 않는다. 초기화 직전 UndoMode를 저장하고 이 새 문서에 한해 Undo 기록을 끈 상태에서 metadata를 쓴 뒤 원 mode(신규 관리 문서는 1)를 복원한다. 원 창이나 이미 편집된 문서의 Undo stack을 끄거나 비우지 않는다. 초기화 전 사용자 Undo/편집이 있으면 `IDENTITY_INIT_NOT_FRESH`로 차단한다.

변경 허용값은 metadata의 `document_id`와 `portable_origin={source_reference,document_member,authority:'HISTORY_ONLY'}`뿐이다. child의 local ID도 binding의 member→ID 표에서 가져온다. 원 native source/모델/관측 hash, job origin, candidate/Boolean/mesh/조건/FEM 바인딩은 재작성하지 않는다. 같은 materialization의 반복 child occurrence는 하나의 local child 문서를 사용하지만 별도 target의 mutable child와 합치지 않는다.

검증 기록은 **XLink path diff**와 **IdentityInitializationReceipt**를 분리한다. 후자는 open_id/member·source/local ID·metadata before/after·허용 key diff·UndoMode 복원·추가 recompute 0을 기록한다. metadata 외 feature/property·shape/mesh/조건/Placement가 달라지지 않았는지는 기존 Pre 기하 보존 관문으로 검사한다. 원 BREP/Boolean 검사를 느슨하게 하거나 가짜 tolerance를 도입하지 않는다. 불일치/초기화 실패에서는 새 문서의 attach/register를 멈추며 원 창은 그대로 둔다.

saved/DERIVED_BASE의 `remember_open` 파생 manifest에는 `new_design_branch=True`와 새 local identity를 넘기고 원 archive manifest는 변경하지 않는다. NATIVE_SAVED working에는 그 flag를 새로 켜지 않으며 현재 target의 저장 identity를 검증한다. DERIVED_BASE 및 saved import는 `Project.last_save=None`, `_saved_graph_version=None`으로 **현지 미저장**이다. 여기의 초기화는 saved/DERIVED_BASE에만 수행한다. 원 revision은 `source_reference`에 표시한다. native metadata를 그대로 둔 constructor override만으로 첫 Save 시의 ID 불일치를 뒤로 미루지 않는다. 이미 NATIVE_SAVED인 working target은 그 target의 exact 저장본임을 대조해 기존 saved attach를 사용한다. 초기 ID는 사용자 Undo 항목이 아니며 이후 치수/조건 편집의 Undo/Redo는 local ID를 유지한다. `Project.save`에서 metadata ID가 local owner와 다르면 `_transaction('Initialize Lab project identity',...)`로 고쳐 통과시키지 않고 `OWNER_IDENTITY_CHANGED`로 거절한다. 일반 legacy 문서의 초기 저장 경로는 별도로 유지한다.

saved import의 첫 Save/취소/실패/등록·head 복구는 §3.3을 따른다. N0 예약이 제시한 새 root를 기존 `Project.save(path=...)`에 주고 처음부터 끝까지 같은 live ID를 쓴다. publish 후 owner.native_target만 결속하며 broker 문서 ID 집합은 바꾸지 않는다. 원 target·source archive·다른 창의 selection/Undo는 불변이다.

이 인도의 새 portable materialization은 충돌을 피하기 위해 기본적으로 별도 FreeCAD process에서 수행한다. 같은 target의 확인된 기존 working 창만 §3.3에 따라 activate한다. 같은 saved command 재확인 외에 같은 source ID를 가진 원 창을 재사용하지 않는다. 파일 Name/Label을 바꿔 native identity 충돌을 숨기거나 다른 열린 문서를 닫지 않는다.

### 5.5 누락·내용 변경 복구

기존 `.caepre`가 기록한 missing XLink에 expected child hash가 없을 수 있다. **그때는 어떤 새 파일도 ‘동일 내용 복구’로 증명할 수 없다.** UI는 `누락된 부품 선택 → 새 설계 연결`로 보내고, 새 owner에서 사용자가 실제 Link를 수정·검토·저장하여 새 revision을 만든다. 기존 파일의 `unavailable_dependencies` 항목을 제거해 기존 revision을 완성본으로 둔갑시키지 않는다.

기존 pin이 있는 원 child가 단순 이동한 경우는 exact child bytes/type/locator 확인 후 derived copy의 위치만 수리한다. 동일 파일명·Label 또는 shape 크기만 같은 다른 파일은 거절한다. 현재 lookup 실패를 막기 위해 최신 child로 자동 대체하지 않는다.

FEM/mesh의 외부 companion이 있는 경우 기존 frozen/native metadata가 선언한 파일만 포함한다. 일반 FeaturePython 객체가 임의 파일을 읽는 경우 이 packet만으로 closure를 증명할 수 없다. 알려진 file-bearing feature adapter가 없으면 incomplete로 표시하고, 일반 FreeCAD 사용 자체를 막지는 않는다. 사용자 macro/addon의 무제한 의존 수집은 이번 범위가 아니다.

## 6. Post dependency closure와 reader 계약

### 6.1 단일 format codec을 네 경로에서 공유한다

추가 pure module `caelab/native_post_dependencies.py`를 Post 담당이 작성한다. ParaView를 import하지 않는다. 등록, saved-source inspection, `_retained_reader_binding`, repair의 closure 비교가 같은 parser를 호출한다. 물리 데이터 reader/해석기를 새로 구현하는 것이 아니라 **어느 파일을 읽는지의 참조 문법만** 해석한다.

| codec | 허용된 참조 위치와 보존해야 하는 의미 | 처리 |
|---|---|---|
| `pvd_v1` | `VTKFile[type=Collection]/Collection/DataSet@file`; ordinal·timestep·group·part 등 나머지 attribute | source 등록의 VTU child 제한 유지. 시간/행 정렬·중복 timestep 삭제 금지 |
| `vtk_parallel_xml_v1` | `PUnstructuredGrid/PPolyData/PImageData/PRectilinearGrid/PStructuredGrid` 아래 `Piece@Source`; ordinal/Extent/GhostLevel | 각 종류에 대응하는 serial VTK leaf까지 닫음. `file`만 순회하는 기존 누락 교정 |
| `vtk_composite_xml_v1` | VTM/VTPC/VTPD의 검증된 dataset subtree 아래 `DataSet@file`; 부모 구조·index/name/ordinal 전체 | 계층 locator는 `(tag, ordinal, 원 attributes)`의 순서열로 보존. Block만 있다고 가정하지 않으며 unknown 구조는 거절 |
| `vtk_serial_leaf_v1` | VTU/VTP/VTI/VTR/VTS의 단일 파일 데이터 | bytes 그대로 보존. appended raw binary를 일반 XML 재직렬화하지 않음 |
| `table_leaf_v1` | 기존 CSV/VTT table reader의 명시 파일 | bytes 그대로. 인코딩·delimiter·열/단위는 reader/기존 metadata 유지 |
| `declared_companion_v1` | 기존 dynamic/contact/shell/beam/curve metadata가 선언한 파일 세트 | 기존 verify API와 함께 사용. 별도 임의 JSON path 탐색 금지 |
| `pvsm_reader_v1` | 아래 ReaderBinding이 특정한 `Property/Element@index` | 실제 입력 property만 변경. 다른 문자열, scripts, domain 정보는 실행 입력으로 승격하지 않음 |

VTK parallel의 `Piece@Source`와 serial 파일의 raw appended data 예외는 공식 format 문서로 보충 확인했다. 위 codec 이름·허용 정책·구현 배치는 이번 설계의 결정이다.[W-VTK]

container XML은 8 MiB, depth 16, 전체 native file 수는 기존 4096 한도와 portable 전체 한도 중 작은 값, Pre는 기존 1024를 사용한다. 기존 더 좁은 PVD 1024 dataset 한도도 유지한다. 총 bytes는 실제 local_input_max_bytes/portable 한도 중 작은 값이며 사용자가 명시한 상한을 자동 올리지 않는다. large leaf는 stream hash하고 전체 RAM에 읽지 않는다.

DTD/entity, URL/network input, absolute 또는 parent-escape container child, 경로 충돌, 무한 cycle, 알려지지 않은 참조 구조는 실패다. 알려진 XML type여도 내부 참조가 지원 구조 밖이면 `UNSUPPORTED_DEPENDENCY`다. 같은 child의 반복 사용은 정상이며 occurrence/ordinal edge는 보존한다.

### 6.2 reader 지원을 extension과 혼동하지 않는다

초기 **직접 결과 등록/추가**의 지원은 기존 VTU/PVD와 명시 VTT 경로다. 이를 보존한다. 저장 프로젝트의 auxiliary/retained reader는 별도 exact binding을 통해 위 codec으로 닫을 수 있다. codec이 PV* 파일을 열거할 수 있다는 것만으로 native reader의 복원 지원을 주장하지 않는다.

`ReaderBinding`은 다음 값으로 고정한다.

```text
reader_key: saved PVSM의 (proxy_group, registration_name, saved_proxy_id)
reader_type: saved Proxy@type와 원 native GetXMLName()의 일치값
file_property: 현재 지원 계약에서 확인한 property name (v1은 FileName)
input_slots: [{element_index, original_value, member_id}]
source_ref: managed source key 또는 null
history_origin: {object_ref, revision_id} 또는 null
codec_ids: 실제 사용하는 dependency codecs
metadata_binding: exact native declaration pin 또는 null
```

saved_proxy_id는 **그 PVSM 내부 locator**다. 새 session의 global ID와 비교하지 않는다. 로드 후 registration name/type/ordered inputs를 다시 읽어 actual proxy를 결속한다. 같은 이름 등록 2개, 서로 다른 type, 입력 슬롯 수/순서 변화, saved id가 다른 proxy를 가리키는 경우 거절한다. 현재 dict comprehension으로 중복 등록을 덮는 위치 앞에 중복 검사를 추가한다.

v1 실행 reader 계약은 원 저장 시 실제 source/aux reader의 type·file property와 알려진 file codec의 조합을 기록하고, 설치된 target이 그 exact native type/property를 제공하는지 확인한다. 원 저장이 live native save가 아니라 raw PVSM 반입이면 지원 type/property whitelist와 별도 native preflight가 필요하다. 이미 알려진 `XMLUnstructuredGridReader/PVDReader/XMLTableReader` 외 type은 실제 public fixture로 source→target readback을 확인한 조합만 registry에 추가한다. **native runtime이 아직 없는 개발 환경에서 type 이름을 추측해 지원 등록하지 않는다.** unsupported 조합은 raw 보존과 문제 위치 표시만 하고 COMPLETE_REOPEN을 반환하지 않는다.

**구현할 v1 reader descriptor 표**는 다음으로 고정한다. 이 표는 지원 완료 목록이 아니라 실제 source PVSM과 target native readback으로 검사할 타입 목록이다. 모든 항목은 proxy group `sources`, 실제 파일 property `FileName`을 사용한다. `one`은 슬롯 1개, `ordered`는 저장된 1개 이상의 슬롯을 순서 그대로 유지한다. 이름이 유사한 다른 proxy로 자동 전환하지 않는다. 현재 direct-source 등록 제한과 프로젝트 내 reader 복원 범위는 별개다.[W-READER]

| 파일/입력 | exact native reader type | 슬롯 |
|---|---|---|
| VTU / PVD / VTT | `XMLUnstructuredGridReader` / `PVDReader` / `XMLTableReader` | ordered / one / ordered |
| VTP / VTI / VTR / VTS | `XMLPolyDataReader` / `XMLImageDataReader` / `XMLRectilinearGridReader` / `XMLStructuredGridReader` | ordered |
| PVTU / PVTP | `XMLPartitionedUnstructuredGridReader` / `XMLPartitionedPolydataReader` | ordered |
| PVTI / PVTR / PVTS | `XMLPartitionedImageDataReader` / `XMLPartitionedRectilinearGridReader` / `XMLPartitionedStructuredGridReader` | ordered |
| VTM / VTPC / VTPD | `XMLMultiBlockDataReader` / `XMLPartitionedDatasetCollectionReader` / `XMLPartitionedDatasetReader` | ordered |
| CSV | `CSVReader` | ordered; 저장된 delimiter/encoding 관련 property 불변 |

reader 표와 함께 codec별 양성 fixture 및 지원하지 않는 nested 참조 음성 fixture를 인도한다. type/property의 실제 존재와 closure 양성 검증이 없는 조합은 capability에 `NOT_VERIFIED`로 남기고 complete opener에서는 거절한다. source 입력과 native auxiliary 입력이 같은 reader_name을 공유하면 둘을 따로 매핑해 덮지 않는다. 중복 binding이 완전히 동일한 경우만 합치고 불일치는 corruption으로 처리한다. old `retained_reader`가 가리킨 파일과 최근 `result_file`이 다르면 둘 다 각각의 역할로 보존한다.

### 6.3 저장 프로젝트의 실제 closure

`post_project_files`는 아래 선언을 모두 소비한다.

- 선택한 `project.json` bytes, 그 `workspace_file`의 PVSM, native revision pin.
- `sources[*].entry_path/source_pins/native_metadata/registration_origin`의 실제 필수 companion.
- `native_readers[*].input_paths`, `native_reader_files` 및 PVSM의 일치된 actual FileName slots.
- `analysis.objects[*].history[*].result_file/result_files`, `retained_reader`, 과거 applied `bindings/dependencies`가 지칭한 정확한 history record.
- 기존 saved draft/Undo/redo/선택에서 선언한 object/source reference, `native_relocation_basis`의 history별 exact 슬롯/원 basis 및 `native_history_availability`의 선언된 누락. 현재 position만 보고 나머지 history의 파일을 버리지 않는다.
- 기록된 field/curve/measurement의 원자료 복귀에 필요한 명시 sidecar. source frame만 복사하고 beam/shell/contact 선언을 버리지 않는다.

`parent_project`, 원 job ID, `relocations`, `original_file`, generic narrative path는 자동 수집을 위한 지시가 아니다. 이전 프로젝트 폴더를 재귀 복사하지 않는다. history가 필요한 원파일을 pin과 함께 명시하지 않았으면 `HISTORY_DEPENDENCY_UNBOUND`를 반환한다.

원 native_readers manifest에 container만 pin돼 있고 child pin이 빠진 과거 저장본은 구분한다. child 파일이 지금 존재한다고 **과거에도 그 bytes였다는 증거가 생기지 않는다.** legacy source는 incomplete로 남긴다. 사용자가 `현재 자료로 새 저장본 만들기`를 명시하면 현재 세트를 새 revision으로 snapshot한다. 원 saved_revision을 그대로 강화해 완료 처리하지 않는다.

### 6.4 derived path 전략

기본은 각 source input set의 상대 directory layout을 유지한다. 따라서 PVD의 `DataSet@file`, composite/parallel child 경로는 보통 바꿀 필요가 없다. 두 source가 같은 `frame0.vtu`를 갖더라도 별도 namespace 아래 둔다. leaf 이름 평탄화·basename lookup·time series 재정렬은 금지한다.

container 경로 수정이 불가피한 경우 old parent pin과 exact edge locator에 결속된 **derived container**만 만든다. allowed attribute 외 XML 구조·timestep/index/group/part/Extent가 동일한지 검증한다. 원 container pin과 derived pin을 함께 `RelocationRecord`에 기록한다. 원 source revision과 raw result 해시를 새 값으로 바꾸지 않는다.

PVSM은 `source_repair._rewrite_reader_paths`를 확장해 전체 ReaderBinding을 받는다. 기존 sources/native_readers signature도 유지한다. FileName 외 property는 해당 reader의 명시 contract가 있는 경우만 처리한다. `Domain/FileList`의 정보 문자열을 일반 search/replace하지 않는다. reader가 실제 사용하는 속성을 식별하지 못하면 성공이 아니다.

`project.json`의 current 경로 투영은 `project_root`, `workspace_file`, source `entry_path/source_pins`, `native_reader_files`의 path key, reader `input_paths`, history `result_file/result_files/retained_reader`의 path에 한정한다. history의 recipe/graph/bindings/source_revision·물리 metadata는 자동 재해시하지 않는다. `source_stamps`가 file property를 제외하는 것은 **managed 원 source**뿐이다. retained analysis reader의 FileName은 input bindings에도 남으므로 §6.4.1을 graph와 bindings 양쪽에 적용한다.[S-WORK][C-REVIEW]

### 6.4.1 graph·retained upstream bindings의 동일 source-basis 비교 — R1

`Workspace.source_stamps`는 원 source일 때만 file property를 제거한다. retained reader A를 입력으로 쓰는 B에는 `B.bindings[A].properties.FileName`이 남고 `_verify_record`는 이 bindings를 graph보다 먼저 비교한다. `describe`도 직접 비교한다. **graph helper만 고쳐서는 정상 이동을 통과시킬 수 없다.** 일반 `source_stamps`/`analysis.graph_signature`의 actual-current 반환과 새 Validate/Apply의 입력 동결 의미는 바꾸지 않는다.[S-WORK][C-REVIEW]

**하나의 history별 basis.** 다음 자료형은 `native_project_contract.py`에 두고 N2가 검증/투영 로직을 작성한다. `H`는 해당 기존 함수의 canonical digest이며 숫자·property encoding을 바꾸지 않는다.

```text
HistoryKey = {object_ref, revision_id, revision_sha256}
  # revision_sha256 = H({id, recipe, graph, bindings}) of this exact history
PostHistoryBasis = {
  version:1, history:HistoryKey,
  bindings_sha256:H(original bindings),
  graph_sha256:H(original graph),
  retained_graph_sha256:H(original retained_graph)|null,
  slots:HistoryPathSlot[]
}
HistoryPathSlot = {
  site: graph | retained_graph | binding,
  binding_ref:str|null,                    # site=binding에서만 upstream ref
  upstream:HistoryKey|null,                # binding은 exact A history; graph는 해당시만
  reader_key:{proxy_group,registration_name,saved_proxy_id},
  reader_type:str, output_port:int, file_property:FileName,
  value_shape:scalar|list, slot_count:int, element_index:int,
  basis_value:str,
  member_id:MemberID, closure_member_ids:MemberID[],
  closure_sha256:str                       # 아래 명시한 원 member/edge 집합 digest
}
```

`reader_key.saved_proxy_id`는 **basis를 기록한 PVSM 내부 locator**이지 live proxy ID가 아니다. site=graph/retained_graph는 해당 graph의 registration-name node, site=binding은 `bindings[binding_ref].properties`의 top-level file property 슬롯에만 적용한다. 임의 path/XPath를 받지 않는다. scalar는 slot_count=1/index=0, list는 원 길이·순서 그대로다. binding의 upstream.revision_sha256는 원 `bindings[ref].revision`과 같아야 한다. graph/retained_graph의 기존 `property_encoding`도 유지한다.

`closure_sha256`는 slot이 가리키는 원 Member의 id/role/bytes/hash와 그 아래 exact DependencyEdge 목록(순서·time/part/group·metadata 포함)을 canonical 정렬/보존한 digest다. 원 member와 파생 member의 bytes가 다르면 **기존 RelocationRecord의 정확한 허용 XML diff**로 증명해야 한다. 같다는 hash를 새로 적어서 원 파일을 바꿔치기하지 않는다. 동일 bytes라도 등록된 slot이 아닌 제3 경로로 옮긴 것은 현재 binding 불일치다.

**durable 위치와 재복사.** 관리 Post의 optional `project.json.native_relocation_basis={version:1,histories:PostHistoryBasis[]}`에 저장하고, registration은 검증된 동일 자료를 `NativeSnapshotRecord.relocation_bases`에 결속한다. 새 raw/legacy의 최초 basis는 그 exact project/PVSM/history/retained_reader와 실제 pin 증거에서만 만든다. 추론이 필요한 슬롯은 `HISTORY_BASIS_UNBOUND`로 남긴다. 원 history의 core/digest 안에 basis를 넣거나 history의 path/hash를 수정하지 않는다.

새 Save는 기존 history의 basis_value·core digest·원 encoding을 유지한다. 새 Validate/Apply가 만드는 history만 **그 시점 actual source_stamps/graph**를 원 basis로 새로 등록한다. 그 즉시 원 값/actual reader 결속을 캡처하고, 아직 PVSM이 없으면 native SaveState 뒤 일치하는 저장 proxy locator를 확정해 발행한다. 저장 단계에서 현재 값을 다시 읽어 과거 Apply의 expected 값을 덮지 않는다. 새 저장 project의 basis는 **native 저장 완료 반환 전** N2가 같은 codec/member mapping으로 확정한다. N0가 완료된 native 파일을 사후 수정하지 않는다. 새 snapshot에서 member IDs가 달라지면 N0의 verified member/edge mapping을 반환받아 N2가 **native commit 전** 새 manifest의 `member_id/closure_member_ids`와 그 구조 digest만 투영한다. N0는 그 완료된 파일을 등록할 때 같은 의미의 새 sidecar를 만들고, 과거 raw manifest와 이미 완료된 native 파일은 수정하지 않는다. 기존 history의 bindings/graph/revision_sha256는 불변이다. 현재 working 문서의 조작에 불필요한 old root/copy1 파일을 열어 basis를 복구하지 않는다.

예: B0는 원 위치의 A0 경로를 basis로 갖고, copy1에서 새 Apply한 B1은 copy1의 A0 경로를 basis로 갖는다. copy2에서 **각 history의 basis 슬롯→그 copy2의 verified member destination을 직접 1회 대응**한다. B0→copy1→copy2 문자열 치환 chain이나 전역 '마지막 경로' 표를 사용하지 않는다. 같은 upstream A의 현재 editor cursor가 A1이어도 B0/B1의 retained 검증은 `_retained_dependencies`가 지정한 A0를 읽는다.

**runtime 검증 순서.** N0가 현재 open/repair의 immutable input·materialization ID·파일/edge mapping을 검증한다. N2 `verified_history_slots`는 이 mapping과 해당 history basis를 대조하고 실제 reader의 registration/type/port/file property/ordered 값·현재 파일 pins/closure를 검증해 transient `VerifiedHistorySlots`를 만든다. 제3 경로, 순서/shape 변화, 잘못된 history, 원 metadata·배열·Input/port 변경은 허용 diff가 아니다. proof는 현재 owner generation/reader stamp에 결속하고 current 변경 뒤 재사용하지 않는다. view poll은 cached 파일 검증 증거를 현재 stat/slot에 대조할 수 있으나 불확실하면 SAME이 아니라 UNAVAILABLE이다.

```python
# caelab/native_post_dependencies.py — pure, native I/O 없음

def graph_on_source_basis(actual_graph: dict, *, expected_graph: dict,
                          history_basis: dict, verified_slots: object) -> dict:
    """검증한 graph/retained_graph 슬롯만 history 원 basis로 투영한 비교 사본.
    기존 graph sha256를 같은 encoding으로 비교용 재산출. 원/actual mutation 0."""

def bindings_on_source_basis(actual_bindings: dict, *, expected_bindings: dict,
                             history_basis: dict, verified_slots: object) -> dict:
    """exact upstream revision과 current destination이 모두 일치하는
    properties.FileName 슬롯만 투영. revision/metadata/다른 property는 그대로."""
```

순수 helper에 public relocation dict를 주어 임의 문자열 치환을 허용하지 않는다. 실제 proof 생성은 §11.5의 native `verified_history_slots`가 수행한다. 필터 type·Input/port·배열·성분·그 밖의 property는 원 비교 그대로 유지하며 mismatch를 지우지 않는다. source basis 숫자 hash 재산출은 검증 사본에만 적용한다.

**호출부별 의미를 구별한다.** N2 `compare_history_inputs(workspace,obj,record,mode=...)` 하나가 아래 두 모드를 제공한다. 결과는 `HistoryInputCheck={state:SAME|DIFFERENT|UNAVAILABLE,mode,revisions,issues,comparison_bindings}`다. 이 state는 입력 비교이지 결과 수치/공학 승인 상태가 아니다.

| 호출부 | mode와 비교 대상 | 처리 |
|---|---|---|
| `_verify_record`의 정상 계산 graph | `retained`; `_retained_dependencies`로 exact upstream history 선택, pending/_verify_inputs 유지 | actual source_stamps→verified slots→bindings_on_source_basis 비교를 **graph 전에** 수행. 불일치는 INPUT_CHANGED, 누락은 SOURCE_UNAVAILABLE. 뒤에 graph projection과 기존 output/물리 검사 유지 |
| `_verify_record`의 retained-only output | 기존 실제 retained_reader·closure·값/mask 검사 | 원 입력 누락에도 검증된 과거 결과 읽기는 가능. 이 예외를 B의 정상 graph 입력 검증 면제로 확대하지 않음. 저장된 retained_graph 비교에는 같은 slots 사용 |
| `describe.current_inputs_differ` | `current`; **현재 editor cursor**의 actual source_stamps | current revision이 expected와 같을 때만 FileName 투영. A1을 A0로 바꾸지 않음. SAME→false, DIFFERENT/UNAVAILABLE→true와 별도 input_comparison_status/이유 표시 |
| 새 preview/Validate/Apply | current actual 입력 | source_stamps 반환을 투영하지 않고 새 bindings 작성. 이전 basis를 새 history에 복제해 현재 변경을 감추지 않음 |

따라서 이동만 한 A0→B0는 현재 변경 표시가 false다. editor가 A1을 가리키면 B0의 **과거 결과 검증은 통과할 수 있어도 현재 입력 다름은 true**다. 일반 source_stamps가 전역적으로 옛 경로를 반환하도록 바꾸지 않는다. 건강한 native 동작·Undo/Redo·부분 보존은 이 두 의미를 공유한다.

새 Save의 결과 export가 새 파일을 만들더라도 기존 retained reader를 다른 파일로 retarget하지 않는다. actual reader 세트와 새로운 result_files가 다르면 모두 보존하고 각 슬롯을 따로 결속한다. native repair에서도 같은 basis/verified slot을 사용해 graph와 bindings를 함께 확인한 뒤에만 commit한다.

### 6.5 코드 실행·비표준 proxy·환경값

PVSM의 `ProgrammableSource/ProgrammableFilter`, writer/extractor, 외부 script·plugin·원격 server 의존은 plain file 이동과 다르다. 이동 검사는 그것을 실행하지 않는다. raw bytes는 보존할 수 있지만 자동 복원 대상은 현재 adapter가 확인한 built-in reader/표시 pipeline과 기존 제품의 retained 분석이다. 미검증 실행 proxy는 branch로 표시하고 직접 실행하지 않는다. 기존 제품이 관리하는 비교/분석 proxy는 재실행 대신 검증된 result_files를 사용한다.

원 project에 남은 `service_url/desktop_python/repo_root/origin_job_id`는 archive에서 history로 보존할 수 있다. **derived current project에서는 이 실행용 top-level 연결 필드를 제거**하고 현재 explicit launcher context만 주입한다. credentials/token/operator config가 원 native payload에 포함된 것으로 확인되면 무단 strip 후 동일 원본이라 주장하지 않고 copy를 차단하여 사용자가 정리한 새 저장본을 선택하게 한다. 주변 config·PID·session 파일은 수집하지 않는다.

## 7. Post 열기·재개·부분 복구

### 7.1 같은 opener 사용

연결 GUI의 기존 `apps/research/desktop.py::_post`에는 `_native_project_ticket`이라는 private 추가 인자를 둔다. 원래 `--input-id` 결과 열기는 유지하고, `native_post_project`일 때만 검증된 파생 `project.json`으로 `--project` 분기를 사용한다. 이 경우 기존 별도 pvpython의 `external.open_result/save_project` 준비를 **다시 호출하지 않는다**. 이미 저장한 분석을 새 결과 viewer로 바꾸지 않는다.[A-DESKTOP]

로드 순서는 다음과 같다.

```text
native_project_read / prepare_open
  → exact raw/snapshot + 현재 local roots 확인
  → final 위치의 새로운 working folder에 derived project/PVSM 생성
  → local 실행 환경을 주입한 기존 _post / startup
  → commands.restore_workspace
  → external.restore_workspace의 source/analysis/state 검증
  → native LoadState
  → external.verify_readers / metadata readback / restore_selection
  → 기존 Owner / Workspace 생성
  → target + saved ref + 실제 selection readback 완료 보고
```

파일 생성 완료나 process PID 반환은 `OPENED`가 아니다. 원 active source/filter/port/view·association·array/component·time·camera·표시 범례 조건과 history reader를 실제로 확인한 뒤 `OPENED` 또는 구체 `PARTIAL_OPEN`을 보고한다. 현재 `_post`의 LAUNCHED 반환은 transport 상태로 유지하며 native 완료 확인을 추가한다.

### 7.1.1 raw PVSM을 관리 프로젝트로 받아들이는 한 경로

raw PVSM 등록은 exact state와 파일 세트의 **반입 snapshot**이며, 존재하지 않는 project.json/history 또는 실제 native Save를 만든 것으로 표시하지 않는다. `format=pvsm`은 native inspection/명시 반입에는 사용할 수 있지만 `copy_intent=complete`의 관리 프로젝트 출발점은 아니며 `MANAGED_SAVE_REQUIRED`를 반환한다. 일반 native Save State/Open은 계속 사용할 수 있다.

`분석 프로젝트로 저장…`은 새 빈 ParaView process에서 아래 `adopt_pvsm` 하나를 호출한다. 이미 열린 사용자의 raw session을 저장하는 경우에도 같은 admission을 실제 현재 reader 집합에 적용한다. 새 process에서는 정확한 PVSM의 derived copy를 native LoadState하고, 로드된 reader를 saved ReaderBinding과 대조한 다음 **이미 로드된 그 reader**로 sources를 작성한다. `admit_result`를 다시 호출하여 두 번째 reader를 만들지 않는다.

source record에는 실제 entry/ordered pins/type/registration을 담는다. 값/metadata가 필요한 경우 현재 기존 native inspection 함수를 호출한 사실을 기록하며, 물리 선언이 없는 단위·측도·run provenance는 UNKNOWN이다. ordered multi-file 또는 auxiliary reader는 native_readers에 그대로 남기고, one-entry managed source로 둔갑시키지 않는다. 등록되지 않은 실행 proxy/파일 의존이 있으면 적용 가능한 healthy/retained branch와 문제 목록을 분리한다.

이 raw 반입은 역사적 관리 저장본의 재열기가 아니라 사용자가 명시한 **신규 관리 프로젝트 작성**이다. 새 project.document_id와 뒤에 붙일 Owner ID는 모두 OpenBinding.owner_document_id를 사용한다. 기존 `external.save_project`로 새 `external-result` project를 발행하고 기존 `Owner/Workspace`를 붙인다. 이미 관리된 saved import의 첫 Save 정책은 §3.3이며, raw 반입의 실제 새 Save를 원 PVSM에 과거부터 있던 저장 이력으로 해석하지 않는다. 한 번의 명시 반입·저장에 의해 만들어진 **새 native 저장본**만 다시 등록해 complete 사본에 사용한다. 실패하면 raw 원본·기존 창은 보존하고, 새로 만든 process/미발행 파일만 소유 범위 안에서 정리한다. 이 경로에서 solver/새 post.apply/새 비교·측정 결과는 만들지 않는다.

### 7.2 별도 저장본 owner·첫 저장과 기존 pipeline 보호

관리 저장본의 새 materialization은 **새 ParaView process**가 기본이다. 두 intent 모두 §3.3의 독립 owner_document_id를 사용한다. saved import는 native/imports/<open_id> 아래 파생 project의 top-level document_id/project_root만 현지 값으로 초기화하고 원 identity/reference는 portable_origin에 남긴다. PVSM history·recipe·원 source/물리 metadata와 원 project bytes는 바꾸지 않는다. Owner constructor override와 파생 project ID가 서로 일치해야 한다.

`Owner._portable_binding`은 Workspace 생성 전에 설정한다. DERIVED_BASE/saved import는 `saved_revision=None`, saved generation/view marker도 미저장으로 취급한다. 별도 `source_reference/native_revision`만 과거 저장 증거로 표시한다. 실제 local NATIVE_SAVED head를 여는 경우에만 해당 target의 saved 상태를 복원한다. 최초 source가 exact라는 사실로 `dirty=false/현지 저장됨`을 만들지 않는다.

saved 창에서는 source/filter·표시·분석 draft 편집과 기존 Undo/Redo가 가능하다. 첫 관리 Save는 §3.3 새 target 예약을 거쳐 같은 owner ID로 기존 Owner.save_project를 수행한다. commands.project가 읽는 **현지 working project**와 owner.project_root의 새 target root를 함께 바인딩한 뒤 저장하고 source archive는 건드리지 않는다. working reader의 파일을 이동하거나 LoadState를 다시 호출하지 않는다. native 저장 실패는 현재 편집을 유지하고, 성공/등록·head 실패는 저장된 현지 파일을 보존한 채 후자만 재시도한다.

working의 동일 target·expected head·확인된 owner/session은 activate할 수 있다. saved는 동일 command 재확인만 같은 import 창으로 돌아가며 다른 command는 독립 창이다. 원 dirty 분석에 LoadState·ResetSession/Delete를 실행하거나 같은 source ID의 duplicate guard를 완화하지 않는다. 원 measurement/Report launch claim·late selection·origin 복귀는 보존한다. 새 native ticket과 기존 measurement/report origin을 한 launch에 섞지 않는다. [C-REVIEW][W-PV]

### 7.3 재열기에서 실행하지 않는 것과 실제 발생 가능한 동작

`inspect/copy/verify/prepare_open`에서는 native process와 reader/pipeline 실행이 모두 0이다. 명시 native reopen에서는 파일 읽기, native 객체 생성, 표시를 위한 reader/렌더링이 발생할 수 있다. 이를 ‘native 함수 호출 0’ 또는 ‘모든 산술 0’으로 보고하지 않는다. 대신 다음을 실제 counter로 보장한다.

- provider 호출, JobManager solver/Numerical submit, Gmsh/remesh, 운동 계산, **원 자료가 지시한** macro/script 자동 실행은 0. 현재 설치의 검증된 cae_prep/startup 로더를 명시 opener가 실행하는 것은 이 금지 대상이 아니며 native_launch/native_load로 기록한다.
- 제품 `post.apply`, 새로운 비교/측정/보간 결과의 작성, 전체 시계열 분석 재실행, 새 분석 history 발행은 0.
- 이미 계산해 보존한 분석은 `partial_state(retain_applied=True)` 및 Workspace의 retained reader 경로로 읽는다. 원 불일치가 있으면 새 계산으로 통과시키지 않는다.

일반 native visualization filter는 LoadState/렌더링 중 평가될 수 있다는 현실을 숨기지 않는다. 그 필터가 새 공학 분석을 만드는 종류이거나 side effect/실행 코드가 있으면 자동 평가 대상에서 제외한다. **보존 데이터가 없는 분석 branch는 `명시 갱신 필요`로 남기며, 자동 재계산 후 정상 복원이라고 하지 않는다.** 정상 native flow 수용은 단순 결과 reader/표시 filter와 이미 저장한 managed 분석을 사용한다. 범용 pipeline 전체의 무계산 복원을 약속하려고 새 cache/분석 엔진을 만들지 않는다.

### 7.4 누락과 변조는 다르다

- **이동 전부터 명시된 partial:** 사용자에게 `누락 표시 그대로 보관`을 명시 선택하게 한다. available assets·원 project/PVSM·expected pin·repair record는 보존한다. `closure=DECLARED_PARTIAL`, 완전 열기 불가를 유지한다.
- **정상 사본의 원 inventory 파일이 이동 후 유실/변조:** portable 검증은 `BLOCKED`다. `allow_repair=True`로 변조 검사를 생략하지 않는다. exact 복구 파일로 `portable_repair`한 뒤 다시 검증한다.
- **raw archive가 정상이고 current 외부 연결만 누락:** 새 derived project의 부분 열기를 사용한다. known missing source reader, semantic dependent analysis, auxiliary reader의 영향을 exact graph로 계산한다.

현재 `source_issues`는 managed sources를 중심으로 하고, `verify_analysis_files`는 한 history 파일 누락도 전체 예외다. 추가 `post_project_issues`가 auxiliary/retained history 누락을 분류하고 **건전한 history와 잘못된 history를 별도 집합**으로 만들어 기존 partial_state/Workspace에 넘기도록 좁게 확장한다. 기존 verifier를 전역적으로 느슨하게 바꾸지 않는다. malformed/변조 PVSM, type/registration 불일치, 부정한 root는 부분 열기 사유가 아니라 차단 사유다.

retained curve의 semantic dependency는 `_unavailable_curve_names`와 `_retained_dependencies`로 추적한다. current `position`이나 source display name으로 가리킬 revision을 바꾸지 않는다. 없어진 history 결과는 요약/수치 캐시가 있더라도 검증 완료 결과로 노출하지 않는다. 문제 목록은 유지하고 건전한 형제 데이터·view/layout은 남긴다.

### 7.4.1 missing history를 남긴 실제 저장 경로

현재 `Workspace.prepare_save`는 bundle이 없는 history를 즉시 거절한다. 이를 blanket skip으로 바꾸지 않는다. N2 `prepare_history_save`가 현재 owner stamp와 **검증된 원 snapshot의 history/pins**에 결속한 `HistorySavePlan`을 만들고 기존 prepare callback으로 전달한다. 사용자 partial 보관 동의는 이 plan의 정확한 누락 목록에 대한 것이지 hash/type/root 검사를 생략하는 허가가 아니다.[S-WORK][C-REVIEW]

```text
HistoryAvailability = {
  history:HistoryKey, state:AVAILABLE|RETAINED_ONLY|UNAVAILABLE_DECLARED,
  record_sha256:str,
  missing:MissingDependency[], reason_code:str|null
}
HistorySavePlan (trusted, transient) = {
  owner_stamp:NativeOwnerStamp,
  histories:HistoryAvailability[],
  preserve_unavailable:bool,
  source_snapshot_sha256:str, plan_sha256:str
}
```

record_sha256는 해당 source에 보존된 전체 history 원객체의 hash다. history core의 revision_sha256와 혼동하지 않는다. pure issue 분류 결과를 임의 dict로 만들어 save 예외를 해제하지 못한다. plan은 exact owner/session/generation과 현재 history/파일 상태에서 생성하고 실제 저장 직전 및 발행 전에 다시 검사한다.

| 분류 | `Workspace.prepare_save` 동작 | 새 saved record |
|---|---|---|
| AVAILABLE | 기존 `_verify_record`와 §6.4.1을 거친 뒤 기존 export/저장 | 기존 native 저장 의미와 basis 보존 |
| RETAINED_ONLY | 실제 reader·result files/closure·기존 값 검증 뒤 보존 | 이미 있는 결과를 기록. 새 계산 graph/Apply 수행0 |
| UNAVAILABLE_DECLARED | plan에 exact history/원 pin/명시 누락이 있고 사용자 partial 보관 동의가 있을 때만 허용. native export/새 bundle 생성0 | 원 history·recipe/graph/bindings/hash·expected result pins·draft/position/Undo/redo 유지. 실제 있는 검증 assets만 복사하고 missing도 계속 선언 |
| 그 밖의 bundle 없음/reader 교체/변조/plan 이후 추가 유실 | 기존 오류 또는 SNAPSHOT_CHANGED/PIPELINE_CHANGED로 저장 차단 | 이전 저장본과 현재 편집 보존. 이력을 삭제해 통과시키지 않음 |

새 `project.json.native_history_availability={version:1,histories:[...]}`와 snapshot.history_availability에 같은 검증 분류를 기록한다. 누락 history의 원 객체를 고치지 않고 상태를 바깥에 둔다. 원 result path는 증거 문자열이며 새 current file locator는 별도 member/relocation binding이다. 보존 summary는 `과거 기록·원값 미확인`으로 읽을 수 있지만 검증된 수치 결과·계산 입력으로 제공하지 않는다.

이미 source manifest가 선언한 누락 또는 **명시 새 partial native Save에서 확인한 외부 source 부재**만 선언할 수 있다. 기존 immutable registered/portable inventory의 유실·변조는 이 경로로 세탁하지 못한다. 누락이라고 선언되지 않은 required archive member가 사라지면 먼저 정확한 복구가 필요하다. 새 Save 중 파일이 바뀌어도 즉석으로 partial 목록을 늘리지 않는다.

건전한 형제 history와 unavailable history는 같은 Save에 남고 재복사에서도 전체 목록·각각의 basis/pins/누락을 유지한다. cold에서 unavailable에 fake reader를 만들지 않는다. 위치 복구는 exact pins 확인 후 existing repair로 수행하며, 편집 가능한 후속 계산은 기존 명시 Validate/Apply만 한다. `prepare_for_save`의 transient preview 정리·pending 입력 처리·원 Save의 실패/발행 경계는 유지한다.

### 7.5 동일 내용 위치 수리와 새로운 결과

동일 내용 위치 수리는 기존 `content_set`에 의한 파일 세트 비교를 재사용하고, 이번 adapter가 **relative member names·bytes·hashes와 전체 edge·reader type·native declaration 일치**를 함께 검사한다. source_change.py의 내부 전체 구현은 이 packet에 없으므로 이 추가 검사를 기존 함수가 이미 모두 수행한다고 가정하지 않는다. 경로만 바뀌어야 한다. 이름만 바뀐 파일, PVD 한 frame 교체, timestep/group/part 변화, 다른 field declaration은 새 입력 revision이다.

정상 source_ref 수리는 `post.source_repair` → Workbench가 검증한 receipt → `Workspace.repair_source` → 기존 `repair_source`를 사용한다. 현 live graph·native pending property·array status·active view/time·Undo/selection을 보존한다. 도중 예외에는 old reader path와 overlay 상태를 rollback하고 source doc는 바꾸지 않는다.

수리된 branch가 여러 auxiliary/retained reader에 쓰이면 한 `RepairPlan`으로 impact를 먼저 확인한다. plan은 source_ref의 old/new Member 대응, 바꿀 exact reader slots, 예상 source_revision 불변, 현재 owner generation, 영향 history IDs를 가진다. 새 helper는 **한 번의 native transaction**에서 prepare→apply→verify→commit한다. 순차적으로 document.clear/update를 여러 번 반복하지 않는다. 모든 관계가 정상일 때만 current document와 repair 목록을 갱신한다. 이때 새 verified destination에 대해 §6.4.1의 graph와 retained upstream bindings를 **함께** 대조하고 describe의 current 비교도 같은 함수를 사용한다. 원 history basis·core는 변경하지 않는다. 파일·reader 변경 후 검증 실패이면 document/reader/basis mapping 모두 이전 상태로 rollback한다.

partial session에서 source를 옆에 다시 추가하는 기존 경로를 유지하고, retained 분석을 바로 실행 graph로 바꾸지 않는다. 편집 가능한 계산 graph를 복구하려면 사용자가 Validate/Apply한다. source에 expected pin이 없는 legacy missing 경우는 identical repair가 아니라 새 결과 등록이다.

## 8. 공통 portable 통합과 current head

### 8.1 형식 호환성

기존 `caelab.portable-project/1`은 그대로 읽고 쓰며 기존 연구 owner 동작을 유지한다. **native 선택 또는 native saved reference의 closure가 포함된 새 사본만 `caelab.portable-project/2`를 쓴다.** /2는 /1의 fields에 아래 native 구조를 추가한 것이다. /1을 /2로 조용히 덮어쓰지 않는다.

이 구별은 필요하다. 현재 /1 reader는 알 수 없는 native 배열을 검증하지 않은 채 READY로 반환할 수 있다. /1에 필드만 추가해 구형 reader가 native 검사를 생략하는 것을 막는다. /2를 모르는 프로그램은 명시 ‘새 형식’으로 거절하고 원본은 보존한다. /2 reader는 /1의 native 없는 사본을 계속 지원한다.[S-PORT]

```text
portable-project.json (/2의 추가 필드)
  native_contract: caelab.native-project/1
  native_inputs: [{local_input_id, source_reference, snapshot_sha256,
                   receipt_path, snapshot_manifest_path}]
  native_projects: NativeTarget[]
  native_mapping: [{source_kind, source_document_id, source_saved_revision,
                    snapshot_sha256, local_input_id, target_id|null}]
```

기존 `documents`에는 여전히 연구 owner 문서만 넣는다. native-only 사본은 `documents=[]`, native_projects 1개 이상이 가능하다. `SUPPORTED` 연구 owner set에 pre/post를 넣지 않는다. native reference가 history에만 있으면 원본과 등록 closure는 포함하되 mutable target은 자동으로 만들지 않는다.

### 8.2 선택 요청

기존 문자열/`{document_id,saved_revision}` 선택은 변하지 않는다. native 선택만 다음 tagged 객체를 추가한다.

```text
NativeCopySelection = {
  native: NativeSavedRef,
  copy_intent: complete | preserve_declared_partial,
  working_target: true | false
}
```

하나의 원 native document에서 한 개 working 시작 snapshot만 선택할 수 있다. 같은 원 문서의 다른 과거 revision은 archive-only로 함께 포함될 수 있다. source_reference는 exact identity이므로 동일명 다른 project를 덮지 않는다. native 선택이 하나도 없는 호출은 기존 code path로 돌린다.

`draft_policy`는 기존 연구 문서 의미를 유지한다. native selection의 current-memory 상태를 `_selections`의 AcknowledgedReader로 읽게 하지 않는다. 저장·등록이 필요한 native 상태는 선택 생성 전에 native save adapter에서 처리한다.

### 8.3 inspect/copy/verify 호출 순서

**inspect**는 선택을 연구/native로 분리한다. 연구 선택은 기존 `AcknowledgedReader/_selections`를 사용하고 native는 `inspect_native`가 등록 세트/sidecar를 검증한다. 연구 typed reference에서 발견한 native refs도 같은 함수로 닫는다. snapshot마다 raw files·required edges·unavailable·예상 bytes·working 여부를 한 inspection에 합친다. inspect 출력에는 current session 승인 토큰이나 실행 명령을 넣지 않는다.

**create**는 기존 approved inspection·command/session/CAS·size·staging·atomic publication을 사용한다. 먼저 raw original을 복사하고, 그다음 현지 input registration receipt를 같은 검증 함수로 재구성한다. 원 input ID는 새 ID로 대응할 수 있지만 original input.json과 원 snapshot은 archive로 보존한다. 현지 file path와 local input ID만 바뀌고 source document/revision/snapshot identity는 그대로다.

기존 `_Fork.reference`에는 native form의 전용 분기를 먼저 둔다. `typed.document_id`를 무조건 연구 owner map에 넣지 않는다. native old input→local input와 source snapshot을 함께 검증한다. `_Fork.write`는 native immutable inventory, local receipts, NativeTarget/head를 기존 final manifest 전에 작성한다. 연구팀 `_Fork` 관련 WIP와 공유 줄은 root가 한 번 통합한다.

**verify**는 원 inventory·snapshot closure·현지 input receipt·native current head를 모두 확인한다. native head의 새 native revision을 최초 copy 때의 mutable file hash와 비교해 손상으로 오인하지 않는다. saved import의 예약만 있는 새 K는 target으로 열지 않고, 첫 head가 실제 발행된 K는 동일 live ID·새 saved reference의 소유를 확인한다. 대신 현재 head가 가리키는 immutable saved registration과 native manifest/dependencies를 검증한다. 반대로 head가 임의 외부 경로를 가리키면 거절한다.

**open_project**는 기존 연구 owner만 열고 native는 catalog만 반환한다. freecad/paraview 자동 launch는 0이다. 사용자가 해당 모델/분석을 선택한 명시 opener에서만 native를 시작한다. native-only UI는 동일 verify/file helper를 직접 호출할 수 있고 Workbench 인스턴스를 만들지 않는다.

### 8.4 목적지 경로를 staging에서 고정하지 않는다

원본·등록 snapshot·relative binding을 복사하되 **실행용 absolute path를 가진 파생 PVSM/FCStd는 실제 열기를 요청한 최종 위치에서 만든다.** staging 경로를 PVSM에 넣고 rename 후 그대로 여는 오류를 피한다.

```text
<copy>/
  portable-project.json
  portable/originals/native/<snapshot>/...        # exact source bytes, 불변
  workbench/inputs/<D>/input.json                 # 기존 등록 receipt
  workbench/inputs/<D>/native-project.json
  workbench/inputs/<D>/files/...                  # exact registered data
  native/<K>/head.json                           # native 저장 위치 포인터
  native/<K>/saved/...                           # 실제 native owner의 새 저장본
  native/<K>/working/<open_id>/...                # working intent의 검증된 파생/편집 파일
  native/imports/<open_id>/...                    # saved import; 첫 저장 전 target 없음
```

`.caepre` raw/unpack 멤버는 그대로 두고 실제 편집은 working 아래에서 한다. Post derived project_root는 working이면 local target의 root, saved import이면 native/imports/<open_id>의 root다. 첫 저장 예약 후 새 K의 저장 root로 명시 결속하고 원 working reader 파일은 이동하지 않는다. old source/service root로 돌아가지 않는다. 다음 copy는 source의 head가 가리키는 **실제 새 저장본**을 다시 등록·검증해서 포함한다. 오래된 working 임시 파일이나 최근 수정일만 보고 골라 복사하지 않는다.

location-only 재열기는 source snapshot을 바꾸지 않는다. native Save에 의한 실제 새 project.json/.caepre는 새 saved reference이고 원본과 구별한다. current `head.json`은 한 개라 여러 단계 nested mapping을 끝없이 누적하여 해석하지 않는다. recopy 시 모든 current path를 새 copy root 기준으로 한 번만 materialize하고 origin lineage는 history로 남긴다.

### 8.5 보존된 부분 사본과 실패

`copy_intent=complete`에서 필수 파일 누락/미지원 closure는 publication을 차단한다. `preserve_declared_partial`은 **source의 실제 저장 manifest가 이미 선언한 누락**과 미지원 branch를 보존하기 위한 명시 선택이다. 정상이라던 raw member가 copying 중 사라진 경우는 이 모드로 전환하지 않는다.

partial 사본의 저장·운반 검증이 정상이라도 `native_availability=PARTIAL`을 반환하고 `complete_native=false`다. `verify_project.status=READY`는 명시 승인된 partial 구조의 bytes 검증이 끝났다는 뜻일 뿐 완전 native 열기/실행 가능이라는 뜻이 아니다. UI는 ‘사본 작성됨 · 일부 자료 없음’으로 표시한다. 공학 release는 여전히 NOT_RELEASED다.

manifest/input/project 원문 자체가 변조되거나 같은 slot에 상충하는 pin이 있으면 partial 보관으로 통과시키지 않는다. 원 오류와 정상 항목을 보존하며 publication은 실패한다.

### 8.6 source/result/연구 관계와 과거 job

native link의 유일한 자료형은 §3.5 DeclaredResearchLink다. Pre metadata/원 project에 이미 기록된 링크를 읽고 명시 선택한 관계만 sidecar.source_links로 바인딩한다. 순수 native에서 `native_links/source_links=[]`는 정상이며 연결된 연구가 없어도 저장·복사·cold reopen을 완료한다.

`collect_declared_links`는 source 위치와 target form에 따른 exact resolver만 호출한다. native·연구 참조의 순환은 visited exact identity로 끝내며 전체 store/job 탐색을 시작하지 않는다. mutable 입력/옛 root를 따라 새 자료를 수집하지 않는다. 이미 함께 선택된 연구 result는 기존 portable retention을 그대로 사용한다. raw 역사 job은 §3.5 records/output_members로 지정한 실제 bytes만 보존한다.

원 Pre metadata.links의 job ID·origin·operation·state와 Post origin은 HISTORY_ONLY다. copied READY/RUNNING·실패도 원 bytes 그대로 두고 현지 현재 job으로 복구하지 않는다. job_record/retained owner는 **최초 명시 link 생성**의 지정 job 확인에만 사용하고 이미 저장된 link의 copy/cold 경로에서는 controller lookup·harvest·retry·자동 실행0이다. 원파일이 없으면 없다고 표시한다.[A-LINK]

첫 saved-import Save는 원 링크를 새 owner의 live origin으로 바꾸지 않는다. 새 현지 native freeze·job만 현재 owner/session/허가·자원검사를 거친 `DesktopLinks.submit_frozen`으로 만들고, copy/open/save 자체에서는 제출하지 않는다. 새 job은 current 관계이고 다음 저장 시의 역사 기록과 구별한다. runtime 권한은 저장 link로 발급하지 않는다.

## 9. typed reference 연결과 selector

### 9.1 처음부터 허용하는 위치

기존 `connection_graph_refs.TypedReference`를 재사용하되 form `native_pre/native_post`와 resolver 분기를 추가한다. 다음 **이미 선언된 참조 위치**에만 new kind를 수용한다.

| 위치 | 의미 | 복사 시 처리 |
|---|---|---|
| Study `draft.evidence[].reference` | exact native 저장본을 연구 근거로 선택 | current draft/Undo/Redo의 local input_id mapping. 원 archive 불변 |
| Expert `draft.composer.evidence[]` | 저장한 모델/분석을 명시 선택 | identity/metadata 읽기까지만. 연구팀 도구 권한 자동 부여 없음 |
| Report `draft.sections[].asset.reference` | 저장한 source로 이동 | R1 원 A/frozen ref는 그대로, current navigation 별도 |
| Numerical의 이미 허용된 `draft.source` 참조 | 계획의 원 native 출처 | provenance-only kind로 validation한 경우만. solver model binding과 혼동 금지 |
| native Pre metadata / Post project의 optional `native_links[]` | §3.5 DeclaredResearchLink, 순수 native는 [] | source는 snapshot 내부 위치; ExactLinkTarget.reference만 current 탐색 projection. JobHistoryTarget 원 bytes/ID/origin은 HISTORY_ONLY |

현재 Numerical `model_source/method_model_sources`, Simulation/Evaluation의 executable source는 기존 domain validator와 native model parameter 계약을 유지한다. `NativeSavedRef`만으로 실행 가능 backend 설정을 만들어 넣지 않는다. 원 계획이 기존 registered `data_id/native_design` 입력을 사용하면 그 원 frozen 입력을 포함하고 **기존 typed input relocation adapter**가 처리한다. 이 packet에 없는 domain 내부 참조를 문자열 탐색으로 새로 해석하지 않는다.

`document_references(include_history=True)`는 closure 수집에 원 run/Undo/Redo의 native refs를 포함할 수 있다. **발생한 원 제출 인자·원 native bytes·원 Report A는 재작성하지 않는다.** 새 current navigation 또는 명시 current draft의 typed slot만 local mapping한다. 새 매핑 규칙을 각 팀이 따로 구현하지 않고 root의 `project_native_reference`를 사용한다.

### 9.2 graph 노드

native graph는 `live observation`과 `saved snapshot` 노드를 구별한다. live 노드의 AVAILABLE은 실제 저장 증명이 아니다. saved snapshot은 input receipt가 검증됐을 때 exact_reference를 가진다. native-only cold에서도 live host가 없어도 saved 노드와 명시 typed 연구 관계를 읽을 수 있어야 한다. saved evidence의 source 노드와 그 materialization owner 노드는 분리한다. 원 dirty 창·saved import·working target이 함께 있으면 세 live ID와 원 source 연결을 표시하며 snapshot만 같은 창을 합치지 않는다.

새 값의 식별 키는 `native/<kind>/<document_id>/<saved_revision>/<snapshot_sha256>`다. `document/<id>`로만 키를 만들면 Post의 D native owner와 등록 D input이 충돌할 수 있으므로 native resolver에서 분리한다. 과거 result 노드는 원 origin/ref를 유지한다.

### 9.3 selector는 reference 바깥에 둔다

```text
NativeSelection
  version: 1
  native_kind: pre | post
  snapshot_sha256: exact selected snapshot
  selection: PreSelection | PostSelection

PreSelection
  document_member: MemberID
  occurrence_chain: [{document_member, object_name}]
  object_name: native Object.Name
  subelements: [native names]

PostSelection
  source: {registration_name, proxy_type, saved_proxy_id, output_port}
  view: {registration_name, view_type, saved_proxy_id}|null
  association: POINTS|CELLS|ROWS|FIELD|VERTICES|EDGES|null
  array_name: 원 array name|null
  component: {mode:scalar|magnitude|index, index:int|null}|null
  time: {value:finite scene time, data_time_value:finite|null,
         frame_index:int|null}|null
  block: {assembly, selectors[]}|null
  analysis: {object_ref, revision_id}|null
```

selector는 전체 saved project에 묶이며 다른 revision에 자동 재사용하지 않는다. native property/actual arrays/time/block domain을 읽어 존재와 유일성을 확인한다. field 이름으로 MPa/Cauchy/local frame을 추정하지 않는다. 원 native source가 가진 선언 또는 기존 saved metadata가 없는 단위/측도는 UNKNOWN이다.

component.index는 mode=index에서만 0 이상의 실제 component 번호이고 나머지 mode에서는 null이다. time.value는 saved scene time, data_time_value/frame_index는 해당 source의 실제 대응이 확인된 경우에만 기록한다. 시간 목록이 다른 source 사이에서 같은 ordinal을 같은 물리 시간으로 취급하지 않는다. native 단위가 없는 scene time에 초 단위를 임의 붙이지 않는다.

현재 dynamic restore는 scene time이 선언 목록에 없으면 첫 시간으로 대체할 수 있다. **exact NativeSelection 재열기에서는 이 fallback을 사용하지 않는다.** LoadState 이전에 현재 등록 declaration과 saved selector의 actual data time 존재를 확인하고, 선택 불가이면 selection 없는 프로젝트 열기를 사용자가 별도로 선택하게 한다. 전체 project가 정상이라는 이유로 첫 frame을 보여주며 원 선택 성공이라고 표시하지 않는다.[S-POST]

source/view saved_proxy_id는 PVSM locator이고 actual session ID로 직접 SetActive하지 않는다. ParaView 6.2의 assembly selector를 사용하는 기존 정확한 원자료 복귀 연결을 보존하며 flat index를 임의 재계산해 다른 leaf를 선택하지 않는다. native selection readback이 실패하면 전체 project를 열 수 있더라도 `SELECTION_UNAVAILABLE`을 별도 반환하고 다른 component/첫 frame으로 성공 대체하지 않는다.

## 10. GUI 명령·실패·복구

### 10.1 익숙한 메뉴와 짧은 한국어

| 사용자 조작 | 화면/다음 행동 | 실제 호출 |
|---|---|---|
| 프로젝트 저장 | 저장 위치, 저장 중, 저장됨/실패 | 기존 Project.save 또는 commands/Owner.save_project |
| 작업 사본 만들기… | 모델/분석·부품·결과·연구 포함 목록과 총 크기 | explicit native registration 후 portable_inspect |
| 현재 내용 저장 후 포함 | native pending은 먼저 종료/Apply 안내 | 실제 save 성공 후 exact ref 생성, 재inspect |
| 마지막 저장본만 | ‘현재 변경은 포함하지 않음’ | saved reference만 선택, native save 0 |
| 사본에서 열기 | 저장본/작업 사본 중 현재 선택을 표시 | prepare_open → 기존 native opener |
| 위치 다시 연결… | 누락 항목을 고르고 파일/등록 세트 선택 | preview_repair → exact 내용 비교 → 명시 apply |
| 새 결과로 추가 | 바뀐 frame/type/metadata 표시 | 기존 post.source_add; 원 source 보존 |
| 연구에 연결… | 이미 열린/저장한 연구 선택 | 기존 source picker/connection preview/apply |
| 원 저장본 열기 / 현재 작업 사본 열기 | source 개정과 현지 저장 상태/현재 변경을 별도 표시 | 두 intent의 독립 live ID, exact ref / target head를 구별해 opener |
| 과거 저장본 창의 첫 프로젝트 저장 | 새 작업 사본으로 저장 / 취소; 기존 target 덮어쓰기 없음 | 새 K 예약 → 같은 owner로 native Save → 등록 → 첫 head 발행 |
| 다시 옮기기… | 현지 새 저장본과 원 근거 포함 | 같은 copy 경로, source/copy1 없는 cold 확인 |

포함 목록의 기본 열은 `이름 / 종류 / 저장 시각·개정 / 포함 상태 / 크기`다. 해당 부품/reader/결과를 선택하면 native 선택 또는 원자료 보기로 이동한다. 내부 ID/hash/schema는 접힌 진단에만 둔다. 필수 dependency check를 끌 수 있게 만든 뒤 성공 표시하지 않는다.

### 10.2 단축키와 native 독립성

FreeCAD 관리 문서의 기존 File Save/Ctrl+S/Close 저장 연결을 유지한다. 일반 native FCStd Export의 의미도 유지한다. `작업 사본 만들기`는 별도 QAction으로 추가하며 기존 shortcut과 충돌하지 않는 보조 shortcut만 배정한다.

ParaView의 native Ctrl+S는 Save Data다. 현재 제품에서도 이 구별이 남아 있으므로 이번 인도에서 이를 몰래 관리 저장으로 바꾸지 않는다. `CAE 프로젝트 저장`은 메뉴·toolbar와 별도 검증된 shortcut(기본 Ctrl+Alt+S)을 제공한다. 실제 설치에서 이미 점유했으면 shortcut을 배정하지 않고 메뉴 기능을 유지한다. 저장·닫기 plugin 미완료를 해결했다고 주장하지 않는다.[S-CMD][W-PV]

ParaView native Qt/Python과 Research PySide6를 한 process에 섞지 않는다. native helper는 현재 host의 QAction/file dialog/macro/GuiDispatch를 쓰고, 공통 포함 목록 presenter와 데이터 계약만 공유한다. standalone에서도 `Owner/Workspace`를 만들고 `commands.set_save_owner`를 연결할 수 있게 `bridge.start(service_url=None)`을 확장한다. service가 없으면 BrokerIO를 시작하지 않고 local GuiDispatch만 유지한다. 반대로 service 연결 시 기존 owner에 broker만 연결하여 별도 owner를 중복 생성하지 않는다.

Pre의 standalone 저장/열기는 기존 native UI 경로다. 사본 만들기 adapter는 file IO 공통 함수를 직접 호출하며 service 연결은 선택이다. 설치된 앱/runtime의 위치는 현재 실행 환경에서 해석한다. 옛 프로젝트의 실행 파일·원 repo 경로를 실행하지 않는다.

### 10.3 command·취소·응답 유실

NativeCommands의 현재 queued/APPLYING/FINISHED와 완료 재연결을 재사용한다. native saveCopy/LoadState 같은 동기 호출에 실제 없는 즉시 취소를 약속하지 않는다. `취소 요청됨`은 중단 확인과 다르다. 아직 queued면 기존 cancel, 복사 중이면 파일 경계에서 cancel, 원자 발행 구간이면 발행 결과를 먼저 확인한다.

| 끊긴 지점 | 저장한 사실 | 같은 command 재확인 |
|---|---|---|
| native Save 전 | 저장 command queued 또는 미수행 | 미수행이 확인된 경우만 사용자 명시 재요청 |
| Save 완료 응답 유실 | NativeCommands 완료 또는 검증된 local save witness | 같은 saved bytes/개정으로 register만 계속. Save 재호출 0 |
| native input 복사 중 | 미공개 staging·원 pin | 완료한 pin 검증 후 복사만 재개 또는 실패. native 실행 0 |
| portable publication 응답 유실 | 기존 create command와 final manifest | 기존 command 조회로 동일 사본 반환. 새 사본 자동0 |
| native open process 생성 뒤 응답 유실 | launch claim/open_id/현재 대상·native handshake | exact open의 상태 확인. 다른 process 무조건 추가 launch0 |
| native 저장 성공, target head 갱신 실패 | 새 native saved bytes/registration과 첫 저장의 K 예약을 보존 | 기존 target은 old head CAS, 첫 저장은 예약 K에 expected_head=None로 pointer만 재시도. Save·ID 재발급0 |
| native process 강제 종료 | 원 archive와 마지막 저장본, 미저장 상태는 확인 불가 | 원 저장본 읽기 가능. 잃은 memory/undo를 복구했다고 표시하지 않음 |

local standalone에는 같은 의미의 작은 action receipt를 해당 target의 local 운영 영역에 둔다. target 전 saved import의 receipt는 native/imports/<open_id>의 로컬 운영 영역에 있고, 첫 저장 예약/같은 command 재확인에만 사용한다. 이는 명령 재확인 기록일 뿐 새 document owner/실행 scheduler가 아니다. 이 운영 receipt, launch ticket, PID/start time, host token은 portable original/history 목록과 구분하고 새 사본의 활성 명령 디렉터리에 이식하지 않는다.

생산 앱에서 성공한 native 창의 수명은 사용자에게 넘긴다. launcher helper의 finally가 정상 창을 종료하지 않는다. 실패/시험 cleanup에서는 자신이 생성한 정확한 process/child/window만 확인해 닫는다. 전역 `taskkill`·열린 모든 FreeCAD/ParaView 종료는 금지한다. 별도 종료 plugin 없이도 테스트가 소유한 공개 세션의 cleanup은 현재 정상 종료/종료 확인 경로로 검사한다.

### 10.4 다중 창·원본 보존

목적지는 새 폴더 또는 비어 있는 폴더다. 원본, 기존 정상 사본, unrelated working target을 overwrite하지 않는다. 대상 경로 선택 취소는 작업 0이다. 저장 대화의 `아니오`를 `마지막 저장본 포함 승인`으로 해석하지 않는다.

stale generation/head 또는 source 변경은 `변경됨 · 목록 다시 확인`으로 반환한다. 현재 native selection·미적용 입력·연구 composer를 지우지 않는다. 늦은 완료는 그때의 open_id/live ID/target/input/command에 붙이며 현재 다른 파일을 보여주는 창을 덮지 않는다. saved 창 첫 Save 취소는 그 창의 수정도 되돌리지 않고 원 창에는 아무 동작도 하지 않는다. 실패 이유와 복구 위치는 사람이 읽을 이름으로 먼저 표시한다.

## 11. 최종 인터페이스 계약

아래 신규 이름은 이번에 확정한 추가 API다. 기존 함수의 이름을 바꿔 같은 역할을 두 번 구현하라는 뜻이 아니다. public dict와 trusted callback을 구별한다. root는 아래 공통 모듈·wire contract를 한 번만 반영하고 Pre/Post는 같은 자료형을 import한다.

### 11.1 공통 자료형

```python
# caelab/native_project_contract.py — 새 공통, FreeCAD/VTK/Qt import 없음

def validate_native_reference(value: dict) -> dict:
    """§3.1 strict keys/type/kind. I/O·저장·native 실행 없음."""

def validate_snapshot(record: dict) -> dict:
    """멤버/edge/reader 중복·type·한도·closure 선언·자체 hash 검사."""

def saved_basis(record: dict) -> dict:
    """§3.1의 canonical basis. local input_id/path/live stamp 제외."""

def snapshot_reference(receipt: dict, record: dict) -> dict:
    """두 검증 객체가 같은 entry/sidecar를 가리킬 때만 NativeSavedRef 반환."""

def project_native_reference(reference: dict, mapping: dict) -> dict:
    """정확한 snapshot을 보존하고 current input_id만 대응. 원 dict 불변."""

def validate_declared_links(links: list, *, native_kind: str) -> list:
    """§3.5 strict union/종류/명시 source 위치 검사. [] 정상, I/O/lookup0."""

def validate_history_bases(bases: list, *, history_records: dict, members: list) -> list:
    """정확한 history core/digest·reader/site/slot/member/closure 결속 검사."""
```

다음 보조 자료형도 이 파일에서 정의한다.

```text
Issue = {code, native_kind, source_reference|null, member_id|null,
         locator|null, message, recovery, severity}

NativeInspection = {
  version:1, reference:NativeSavedRef, snapshot:NativeSnapshotRecord,
  copy_intent, files:VerifiedFilePin[], bindings:RelocationBinding[],
  issues:Issue[], total_bytes, inspection_sha256
}

RegisteredReplacement = {
  parent_member:MemberID, locator:DependencyEdge locator,
  expected_child:{bytes:int,sha256:str,relative:str}|null,
  replacement_input_id:str, replacement_member:str
}
  # replacement_member는 해당 등록 input.json.files[].relative의 정확한 값.
  # 임의 절대경로/외부 path/호출자 receipt/ArchiveMember 추정은 받지 않음.

RelocationRecord = {
  version:1, source_snapshot_sha256, open_id, target_id:null|K..., algorithm_version,
  derived_members:[{source_member, derived_relative, bytes, sha256,
                    edits:[{locator, old_value, new_value}]}],
  identity_edit:{source_document_id,owner_document_id}|null,
  original_data_unchanged:true
}

NativeOpenRequest = {
  reference:NativeSavedRef, intent:saved|working,
  target_id:null|K..., expected_head:null|{generation,reference},
  selection:null|NativeSelection, allow_partial:bool
}
OpenBinding (trusted; public 요청 객체가 아님) = {
  open_id, request_sha256, open_intent:saved|working,
  source_reference:NativeSavedRef, owner_document_id:str,
  owner_id_map:[{member_id,owner_document_id}],
  target_id:null|K..., expected_head:null|{generation,reference},
  materialization_root, native_save_root,
  verified_input, member_paths, relocation, history_bases
}
NativeTargetSaveBinding (trusted; 로컬 action receipt로 재확인) = {
  save_id, save_command_id, open_id, owner_document_id, target_id,
  expected_stamp:NativeOwnerStamp,
  expected_head:null|{generation,reference},
  creation:NEW_TARGET|EXISTING_TARGET,
  source_reference:NativeSavedRef, native_save_root, request_sha256
}
```

`intent=saved`의 요청 target_id/expected_head는 null이어야 한다. N0가 command별 새 open_id와 owner_document_id를 예약하고 같은 요청 재확인에는 같은 값을 돌려준다. `intent=working`은 target/expected_head 필수이고 request.reference는 expected_head.reference와 정확히 같아야 한다. 다르면 STALE_TARGET이며 latest로 바꾸지 않는다. 두 intent 모두 원 native saved ID를 두 번째 live owner로 쓰지 않는다. selection은 source snapshot에 결속되고 다른 저장 개정으로 이동시키지 않는다.

`NativeTargetSaveBinding.creation=NEW_TARGET`은 현재 saved import의 첫 저장 예약에서만 만들며 target은 미발행 새 K, expected_head는 null이다. EXISTING_TARGET은 현재 owner.native_target과 exact head에 결속한다. ID/session을 바꾸거나 원 target을 선택하는 option은 없다. public 요청의 dict나 복사된 운영 receipt로 이 binding을 생성하지 않는다.

`RegisteredReplacement.expected_child`는 caller가 주장한 값이며 source의 exact edge/native manifest 증거와 반드시 대조한다. replacement_member는 기존 등록된 실제 파일만 지정한다. 동일 내용 수리에는 원 expected pin과 전체 의존 세트·edge/type/metadata가 필요하다. expected_child=null 또는 source 증거가 없으면 identical repair가 아니며 새 current snapshot/명시 새 연결만 가능하다. 예상 pin을 caller가 추가해 과거 기록의 증거로 만들지 않는다.

`IdentityInitializationReceipt`의 key는 `{open_id,member_id,source_document_id,owner_document_id,metadata_before_sha256,metadata_after_sha256,changed_keys,undo_mode_before,undo_mode_after,adapter_recompute_calls,geometry_check}`다. source_document_id는 원 파일에 없으면 null, changed_keys는 document_id/portable_origin의 부분집합, adapter_recompute_calls=0, geometry_check는 기존 검사의 결과다. 이 receipt 자체가 geometry 검사를 대체하지 않는다. old identity가 이미 target의 값이면 metadata write/UndoMode 변경 없이 확인만 한다. 다른 user edits가 있는 문서에는 초기화를 적용하지 않는다.

`DeclaredResearchLink/ExactLinkTarget/JobHistoryTarget/NativeLinkSite`는 §3.5, `HistoryKey/PostHistoryBasis/HistoryPathSlot`은 §6.4.1, `HistoryAvailability/HistorySavePlan`은 §7.4.1의 정의를 여기서 그대로 import한다. 별도 구현자별 alias schema를 만들지 않는다.

### 11.2 기존 input 등록을 확장하는 함수

```python
# caelab/native_project_inputs.py — 새 공통/root

def register_saved(context, source: dict, *, replacements=(), command_id: str) -> dict:
    """SavedCommandSource|SavedFileSource → REGISTERED + reference.
    public replacements를 N0가 검증해 private edge map으로만 전달.
    실제 saved 파일만. native Save·solver·Workbench 생성 없음.
    """

def verify_registered(context, reference: dict, *, full: bool = True) -> object:
    """VerifiedNativeInput. raw entry/all member/sidecar/edge/owner/revision 검증.
    full=False는 source summary 전용이며 portable READY의 근거로 금지.
    """

def read_registered(context, reference: dict, *, facet: str = "summary") -> dict:
    """summary|manifest|dependencies|source_links; read-only, native launch 0."""

def prepare_target_save(context, open_id: str, *, expected_stamp: dict,
                        expected_head: dict | None, command_id: str) -> object:
    """NativeTargetSaveBinding. saved 첫 저장은 새 K 예약, working은 기존 head 검사.
    native Save/head 발행0. 같은 요청에는 같은 K/save_command_id 반환."""

def publish_head(context, target_id: str, completed_save: object, *,
                 expected_head: dict | None, command_id: str,
                 _target_save: object = None) -> dict:
    """실제 native save/등록 뒤 head CAS. 첫 head는 verified NEW_TARGET 예약 필수.
    existing은 exact old head; duplicate는 같은 결과. native Save 재호출0."""

def verify_replacements(context, source: dict, replacements: list) -> object:
    """source edge + 기존 등록 receipt 검증 → VerifiedReplacementMap; native 실행0."""

def bind_declared_links(context, links: list, *, members: list) -> dict:
    """기존 exact resolver로 명시 참조만 확인. 링크·읽기 상태·issues 반환.
    원 job cold lookup0. 관계가 미보존이면 HISTORY_ONLY/UNAVAILABLE 유지."""
```

`context`는 이미 존재하는 input 파일 영역·현재 approved roots·한도·취소 callback·현재 작업 session을 제공하는 작은 **trusted file-access adapter**다. 연결 모드는 Workbench에서 만든다. standalone 모드는 명시 파일 chooser/root에서 만든 `NativeOnlyContext`를 쓴다. NativeOnlyContext는 `workspace/root/session_id/config`와 기존 `native_inputs`/portable IO 호출만 제공한다. 연구 owner·JobManager·native host·provider를 생성하지 않는다. 연구 문서 ID 선택을 받으면 이 로컬 adapter는 거절하고 사용자가 기존 연구 연결을 선택하게 한다.

기존 `Workbench.input_path/native_input`는 `native_post_project`와 `input.json.native_project` pin을 검증하는 좁은 분기를 추가한다. dynamic source의 선택 frame fast path는 일반 result 읽기에 유지하지만 **전체 사본 검사에는 full=True를 강제**한다. metadata_only 검증을 전체 파일 검증 PASS로 승격하지 않는다.

첫 head 발행은 `completed_save.document_id == registered_reference.document_id == binding.owner_document_id == target.working_document_id`를 확인한다. NEW_TARGET의 visible head_generation은 1, copy가 만든 DERIVED_BASE head_generation은 0이고 후속 저장은 기존 generation+1이다. EXISTING_TARGET에서 head가 없으면 새 생성으로 해석하지 않는다. 공개 target_id만 맞고 owner/session/save_command가 다르면 거절한다. source raw 저장 경로·registered inputs·다른 target을 native Save destination으로 선택할 수 없다.

`VerifiedReplacementMap`의 각 행은 parent member/원 locator/검증된 expected pin, replacement input ID/relative, 현재 registration pin과 actual file/closure를 가진다. N0만 기존 `native_input` 검증으로 생성하고 전체 파일 재검사·command signature에 결속한다. public replacements는 source 안이나 `_replacements`라는 body key로 중복 수용하지 않는다.

`bind_declared_links`는 ExactLinkTarget에 기존 `SnapshotReader.resolve(TypedReference((), relation, form, reference))`의 exact-reference 검증을 재사용하며 native form은 native-first resolver를 사용한다. 참조가 unavailable한 기존 저장 링크는 현재 탐색 불가로 보존할 수 있다. 그러나 새로운 유효 관계를 만들 때는 exact_reference 일치가 필요하고, 함께 포함하기로 고른 실제 파일 closure의 실패를 이 상태로 숨기지 않는다. 수동 native-only 저장은 연구 resolver를 요구하지 않는다.

신규 sidecar는 `_register_set`의 opaque native_metadata에 전체 자료를 우겨 넣지 않는다. 공통 등록 후처리 hook으로 staging sidecar를 검증하고 input.json 최종 발행에 결속한다. 이미 발행된 input.json을 사후에 제각각 수정하는 접근은 금지한다.

### 11.3 기존 portable projection의 native 분기

```python
# caelab/portable_project_native.py — 새 공통/root

def inspect_native(context, reference: dict, *, copy_intent: str) -> dict:
    """NativeInspection. 저장/등록/실행 0."""

def collect_native_references(context, typed_references, explicit_selections) -> dict:
    """동일 snapshot dedupe, historical archive/current target 구별."""

def stage_native(context, inspections: list[dict], stage, *,
                 project_id: str, local_ids: dict) -> dict:
    """기존 copy_verified로 original/local input/native target 작성.
    native 절대경로 derived open은 여기서 만들지 않음.
    """

def verify_native(context, manifest: dict) -> dict:
    """immutable native inventory + 현재 head, state/closure/readiness 분리."""

def prepare_open(context, request: dict, *, command_id: str) -> object:
    """현재 위치의 VerifiedNativeInput/OpenBinding/derived files → ticket.
    actual native launch 0; 두 intent의 독립 owner ID를 launch 전에 예약.
    동일 command+input은 같은 ticket, copied open/command는 활성화하지 않음.
    """

def verify_opened(context, open_id: str, actual: object) -> dict:
    """authenticated owner 또는 같은 standalone launcher의 trusted readback만.
    source proof + 독립 live ID + current target/save 상태 + selection을 확인.
    public dict를 완료 증거로 사용하지 않음.
    """
```

`stage_native`가 반환하는 mapping은 §8.1의 native 배열이다. `_Fork.reference/write`는 이 mapping을 받아 기존 연구 current typed reference를 연결한다. source archive는 변경하지 않는다. signature의 `context`를 사용하여 `portable_project.inspect_copy/create_copy`의 native-only 경로가 Workbench 없이 동일 transaction을 수행할 수 있도록 한다. native-only와 혼합 모드가 별도의 ZIP writer/repair 알고리즘을 갖지 않는다.

§8.1의 /2 native arrays는 source closure 여부와 관계없이 모두 검사한다. graph 노드만 추가하고 `_Fork`·verification·open 중 하나를 빼는 인도는 미완료다.

### 11.4 Pre 전용 adapter

```python
# apps/desktop_pre/portable_project.py — 새 Pre 담당

def saved_offer(owner) -> dict:
    """GUI thread, 현재 saved/busy/dirty/연결부품 상태. 저장 0."""

def complete_save(owner, *, expected_stamp: dict, path=None,
                  _target_save: object = None) -> object:
    """기존 owner.project.save 한 번. saved import는 새 target 예약을 필수 확인.
    원 input/archive·다른 target 경로 overwrite를 차단하고 완료 witness 반환."""

def pre_snapshot_files(saved_file, *, approved_roots, _replacements=None) -> dict:
    """native_cad exact closure. _replacements는 N0 VerifiedReplacementMap만. native 실행0."""

def initialize_import_identity(doc, binding: object, *, member_id: str) -> dict:
    """새 working 문서 attach 전 metadata-only, 사용자 Undo 밖 초기화.
    §5.4 IdentityInitializationReceipt; _transaction/recompute/save 호출0."""

def open_bound_project(owner, verified_receipt: object, binding: object) -> dict:
    """두 intent 모두 기존 Project.open→identity 초기화→remember_open/새 owner attach."""

def select_bound_target(owner, selection: dict, binding: object) -> dict:
    """exact member/occurrence/object/subelement 확인 후 native 선택·readback."""

def inspect_repair(snapshot: dict, replacements: object) -> dict:
    """N0 VerifiedReplacementMap에서 동일/변경/expected 없음 구별. 원파일 변경0."""
```

`pre_snapshot_files`는 import 시 FreeCAD를 요구하지 않도록 순수 부분을 `caelab/native_cad` 호출로 제한한다. `complete_save/initialize_import_identity/open_bound_project/select_bound_target`만 native thread에서 실행한다. Core 파일 IO worker가 App/Gui를 만지지 않는다.

Project.open은 `open(self, receipt, *, _portable_binding=None)`으로 확정한다. 기존 receipt-only 호출은 유지한다. 새 binding은 저장된 source·target·현재 open_id를 확인한 Core/standalone 함수가 주입한다. public `pre.project.open`은 종전 `{input_id}` 또는 확장 `{input_id,open_id}`만 받는다. open_id가 있으면 Workbench가 자기 현재 open ticket을 조회하고 requested input_id와 exact source가 같을 때만 receipt/binding을 주입한다. 외부 caller가 path/receipt/binding 내용을 직접 제출하면 거절한다. 반환에는 열린 새 native document, 실제 object/member 대응, source snapshot, 독립 owner_document_id, target_id 또는 null, local_save_state, selection 결과가 들어간다. 첫 저장 전 source saved 상태와 현지 저장 상태를 합치지 않는다. source App document를 바꿔치기하지 않는다.

### 11.5 Post 전용 adapter

```python
# caelab/native_post_dependencies.py — 새 파일, 작성은 Post, root가 공통 소비

def inspect_dataset(entry, *, baseline_pins, approved_roots, limits, _replacements=None) -> dict:
    """exact container/leaf graph. child pin이 빠진 legacy는 incomplete."""

def inspect_pvsm(state, *, saved_readers, source_records, limits) -> dict:
    """reader registration/type/file slots 및 실행 위험 branch, XML만 검사."""

def post_project_files(project_path, *, approved_roots, limits, _replacements=None) -> dict:
    """project/PVSM/source/aux/history/metadata/basis/누락 선언 closure.
    _replacements는 N0 검증 객체; 모든 중첩 codec에 같은 edge map 전달."""

def relocate_container(source, destination, *, verified_edges, member_paths) -> dict:
    """정확한 경로 attribute만. original/derived pin과 allowed-diff 반환."""

# apps/desktop_post/portable_project.py — 새 Post 담당

def saved_offer(owner) -> dict:
    """owner thread에서 dirty/pending/saved/current selection 표시. Save 0."""

def complete_save(owner, *, expected_stamp: dict, _target_save: object = None,
                  _history_plan: object = None) -> object:
    """기존 Owner.save_project. first-save target/부분 history plan 검사 후
    실제 saved manifest의 witness. registration/head는 N0가 수행."""

def derive_project(verified_input: object, destination, *, binding: object) -> dict:
    """typed JSON/PVSM path projection·환경 비활성화·derived pin. LoadState 0."""

def adopt_pvsm(verified_input: object, binding: object, *,
               expected_empty_session: bool) -> object:
    """§7.1.1 명시 반입. actual loaded readers를 재사용해 기존 save 수행.
    실제 native saved project의 CompletedSaveWitness 반환.
    """

def restore_bound_project(verified_input: object, binding: object, *,
                          allow_partial: bool = False) -> dict:
    """기존 commands/external.restore_workspace → Owner/Workspace/readback."""

def preview_repair(owner, replacements: object, *, expected_stamp: dict) -> dict:
    """VerifiedReplacementMap + scope/type/impact/graph/bindings 검사. 변경0."""

def apply_repair(owner, plan: dict, *, expected_stamp: dict, command_id: str) -> dict:
    """기존 source_repair의 rollback 원칙으로 graph+bindings 함께 검증·commit."""

def verified_history_slots(workspace, obj: dict, record: dict, *, mode: str,
                           actual_bindings: dict | None = None) -> object:
    """해당 history basis·실제 upstream reader/type/port/slot·current pins/closure
    → VerifiedHistorySlots. 공개 dict로 생성 금지; 원 history/current mutation0."""

def compare_history_inputs(workspace, obj: dict, record: dict, *, mode: str) -> dict:
    """mode=retained|current. §6.4.1 HistoryInputCheck; source_stamps는 actual 유지.
    current cursor 차이는 path 투영으로 지우지 않음. 새 preview에는 사용하지 않음."""

def prepare_history_save(owner, *, expected_stamp: dict,
                         preserve_unavailable: bool) -> object:
    """현재 history·source proof·명시 누락 검증 → HistorySavePlan. Save/export0."""

def finalize_history_bases(document: dict, *, saved_readers: list,
                           member_mapping: object) -> list:
    """SaveState 후 project.json commit 전에 호출. 기존 basis는 core/원값 불변,
    새 Apply의 캡처는 actual saved reader에 대조. N0 verified member map으로
    §6.4.1의 durable basis를 반환; 완료된 native 파일 사후 변경0."""
```

`derive_project`의 private binding은 target current root, 실제 member paths, source/derived pins, working document ID, original reference, 허용 reader slots만 제공한다. 실제 열기에 쓰는 `Owner.__init__(document_id=None, session_id=None, *, _portable_binding=None)`은 **Workspace를 만들기 전에** 검증된 `_portable_binding`을 설정한다. Workspace 생성 중의 retained graph 검증이 이를 사용할 수 있어야 한다. 로드 후 descriptor를 보고 뒤늦게 binding을 붙이는 구현은 금지한다.

기존 `bridge.start`는 `start(service_url=None, *, log=None, owner=None, _portable_binding=None)`으로 확장한다. 이미 만든 같은 local owner가 있으면 재사용하고, 없으면 이 constructor로 한 번만 만든다. 항상 기존 GuiDispatch/commands.set_save_owner를 연결하되 BrokerIO는 service_url이 있을 때만 시작한다. portable binding은 caller가 전송한 임의 dict가 아니라 검증된 current open ticket의 로컬 객체다. project의 임의 key를 치환하는 callback을 제공하지 않는다. history별 graph와 bindings/path equivalence는 `verified_history_slots`와 두 pure projection이 담당한다. `_verify_record`의 bindings-first 비교와 `describe`의 current cursor 비교가 같은 `compare_history_inputs`를 사용한다. 물리 결과 요약이나 original bindings 해시를 재계산해 mismatch를 숨기지 않는다.

Post 기존 `Owner.save_project(self, *, _target_save=None, _history_plan=None)`에만 private keyword를 추가한다. 기존 무인자 호출은 유지하되 saved import의 첫 Save는 검증된 _target_save 없이는 FIRST_SAVE_TARGET_REQUIRED다. `complete_save`가 두 private 값을 전달하고, working project/저장 root 연결은 같은 owner thread에서 검증한다. Pre의 `Project.save(path=None)` signature는 유지하며 전용 complete_save가 target binding을 확인한 뒤 정확한 path로 한 번 호출한다.

기존 `Workspace.prepare_save(document, folder, *, _history_plan=None)`로 signature를 좁게 확장한다. owner.save_project는 준비된 plan을 closure로 묶어 기존 external.save_project(prepare=...)에 전달한다. bundle 없는 history는 plan의 exact UNAVAILABLE_DECLARED인 경우만 원 record/expected pins를 보존하며 skip-export한다. 다른 bundle 누락/변조/입력변경은 기존 오류로 차단한다. `native_relocation_basis/native_history_availability`를 새 저장 project에 함께 발행하고 AVAILABLE 이력의 record hash는 실제 prepare 결과로, unavailable은 원 record 그대로 결속한다. 일반 history/source_stamps/graph의 저장 알고리즘을 대체하지 않는다.

두 pure path projection의 최종 signature는 §6.4.1이다. 신규 Apply의 exact basis 캡처는 기존 Workspace의 해당 history 옆 메모리 자료에 보관하고 `finalize_history_bases`가 native SaveState의 실제 registration/type/slot과 대조해 확정한다. 기존 history의 expected graph/bindings를 현재 값으로 바꾸지 않는다. N0의 member_mapping이 불명확하면 저장 성공을 게시하지 않는다.

Post 저장에 codec을 연결해 `native_reader_files`와 retained binding의 child 누락을 막는다. raw PVSM 반입은 pure inspection/등록 후 명시 native LoadState와 existing save로 `external-result` project를 만든다. 이때 생성한 native manifest는 **새 관리 저장본**이다. 원 PVSM bytes와 source pins는 별도로 남는다. 부적합 reader가 있으면 보존/partial 상태로 돌아가고 정상 결과 open으로 위장하지 않는다.

### 11.6 Workbench/Client와 실제 GUI 연결

추가 public wrapper는 다음으로 고정한다. 기존 service/router/client에만 노출하며 별도 서버를 만들지 않는다.

```python
# 기존 Workbench에 추가할 method signature만 표시한다. 클래스를 교체하지 않는다.
class Workbench:
    def native_project_register(self, source, *, replacements=(), command_id): ...
    def native_project_read(self, reference, *, facet="summary"): ...
    def native_project_prepare_open(self, request, *, command_id): ...
    def native_project_open_ticket(self, open_id): ...
    def native_project_prepare_save(self, open_id, *, expected_stamp,
                                    expected_head, command_id): ...
    def native_project_save_head(self, target_id, save_command_id, *,
                                 expected_head, command_id, open_id=None): ...
```

`native_project_prepare_open`의 public 반환은 `{status:"PREPARED", open_id, reference, owner_document_id, target_id, local_save_state, warnings, effects}`다. saved에서는 target_id=null, local_save_state=UNSAVED_IMPORT이고 독립 owner ID는 이미 예약되어 있다. Python 내부의 VerifiedNativeInput/NativeOpenTicket을 직렬화해 caller의 권한 객체로 돌려주는 것이 아니다. 이어서 같은 현재 service의 `native_project_open_ticket(open_id)`가 저장된 요청/현재 세션/refs/member pins/목적지 binding을 다시 검사해 기존 local launcher에 필요한 payload를 반환한다. 조회 자체에는 native dispatch가 없다. 오래된 copied open_id, 요청-참조 불일치, 이미 불명확하게 실행된 작업은 새 실행 허가로 반환하지 않는다.

public CLI에는 native `pre/post --native-project-open-id`만 추가한다. `_pre/_post`는 이 ID를 현재 service에서 확인한 뒤에만 private ticket으로 만든다. path/JSON ticket argument로 우회하는 기능은 만들지 않는다. standalone은 같은 module의 `prepare_open`이 반환한 현재 local 객체를 직접 사용하며 service를 흉내 내지 않는다. 정상 open handshake 뒤에는 ticket의 source reference/독립 owner ID/target 또는 null/current session/local_save_state를 확인한다. 원 source ID로 등록된 다른 live owner의 응답은 완료 증거가 아니다. 중복 요청은 확인된 native 창 activate 또는 OPEN_UNCONFIRMED 조회일 뿐 새 launch가 아니다.

`native_project_prepare_save`는 사용자 첫 Save 확인 뒤만 호출하며 source intent·현재 owner stamp·target 상태를 검증한다. public 반환은 `{status:'SAVE_PREPARED', save_id, save_command_id, open_id, owner_document_id, target_id, expected_head, effects}`다. 이 반환 자체가 native 저장을 수행하지 않는다. 일반 `pre.project.save/document.save`의 **그 save_command_id**를 기존 NativeCommands로 제출할 때 root가 예약의 owner/session/generation을 대조해 private `_target_save`를 주입한다. 사용자 path/receipt/binding field를 새 public body로 받지 않는다. 기존 저장 인자/dispatcher를 유지하고 native 전용 helper에서만 이를 소비한다. standalone은 같은 trusted binding을 직접 넘긴다.

`native_project_save_head`의 first-save는 open_id 필수, expected_head=null, 같은 예약 save_command_id의 실제 완료 outcome만 받는다. 기존 target은 현재 owner.native_target과 exact expected head를 대조한다. native 저장 호출 또는 id 재발급은 없다. head 성공 후 target association만 갱신하고 registered document ID 집합은 불변이다. 예약 상태·부분 발행·원 command가 없는 임의 Save 완료 dict는 거절한다.

connected save source는 NativeCommands의 completed command로만 작성한다. standalone caller가 만든 completed result dict를 public API로 전송해 동일 authority로 사용하지 않는다. standalone에서는 같은 process의 trusted object를 local function에 넘긴다. 연결 후에는 이미 로컬에 저장된 실제 파일을 selected_file로 재등록하면 된다.

기존 `portable_inspect/portable_create/portable_verify/portable_repair` 이름·파라미터는 유지하고 tagged native selections와 /2만 확장한다. source/root validation 없이 `input_id`를 임의 만들어 받지 않는다. service가 returned path를 제공하는 것은 현재 검증된 local opener용이고 일반 caller path 입력을 허용하는 것과 다르다.

```python
# apps/research/native_project_actions.py — 공통 GUI presenter/root

def open_native_project(client_or_local, request, *, command_id):
    """prepare_open → 현재 desktop context → 기존 _pre/_post → 완료 readback."""

def copy_from_native(client_or_local, saved_reference, *, linked_selections=()):
    """포함 목록·저장 선택 UI와 기존 portable transaction 연결."""
```

독립 경로를 구현자가 새 launcher로 우회하지 않도록 현재 `_pre/_post`에 다음 private parameter를 추가한다. 원 source/input_receipt/cae_prep/startup, measurement/report/curve origin 경로와 process 생성 방식은 유지한다.[A-DESKTOP]

```python
# apps/research/desktop.py — 기존 함수에 keyword-only 파라미터 추가

def _pre(client, args, *, _local_context=None, _native_project_ticket=None): ...

def _post(client, args, *, _report_origin=None, _report_launch=None,
          _measurement_origin=None, _origin_launch=None,
          _local_context=None, _native_project_ticket=None): ...
```

`DesktopLaunchContext`는 `{python,repo_root,export_root,freecad_executable,paraview_executable,service_url}`의 **현재 설치·현재 실행용 trusted 값**이다. service_url만 null 가능하다. 기존 local executable 확인과 `_folder`를 재사용하고 원 snapshot의 실행 경로에서 만들지 않는다.

connected 호출은 기존 client.desktop_context를 사용한다. native-only 호출은 `client=None`과 로컬 설정/설치 경로로 검증한 `_local_context`를 함께 넘긴다. 이 경우 client.desktop_context/native_input/_spawn 또는 Workbench 생성은 0이다. `input_receipt`와 derived project는 검증된 ticket에서 가져오며, 빈 URL을 가진 fake Client를 만들지 않는다. `service_url`이 null이면 CAE_POST_SERVICE_URL/CAELAB_SERVICE_URL과 원 origin 환경을 제거하고 BrokerIO를 시작하지 않는다. 기존 native owner·현재 process의 GUI command/save와 file IO만 동작한다.

현재 CLI main의 무조건 service 요구는 **research/연결 tool에는 유지**한다. native `pre/post`에서 명시 파일 chooser/등록 snapshot을 선택한 local 모드만 위 context를 허용한다. arbitrary public JSON이 `_local_context`를 지정하는 service endpoint는 만들지 않는다. 현재 native 창에서 여는 `pre.project.open`은 §11.4의 input_id/open_id 검증 후 기존 receipt injection을 재사용한다. raw file 일반 열기와 연구 exact reference 열기 모두 native opener는 같고, 앞의 권한·source 검증만 다르다.

### 11.7 오류와 effects

공통 API의 실패는 `{status, issues, source_reference, command_id, effects}`를 반환한다. 최소 code는 다음을 포함한다.

`SAVE_REQUIRED`, `MANAGED_SAVE_REQUIRED`, `BUSY_EDIT`, `INPUT_CHANGED`, `SAVE_UNCONFIRMED`, `SAVE_PUBLISHED_HEAD_PENDING`, `SOURCE_UNAVAILABLE`, `CONTENT_CHANGED`, `DEPENDENCY_UNBOUND`, `DEPENDENCY_CYCLE`, `ROOT_DENIED`, `UNSUPPORTED_READER`, `UNSUPPORTED_DEPENDENCY`, `READER_BINDING_CHANGED`, `SNAPSHOT_CHANGED`, `STALE_TARGET`, `COMMAND_CONFLICT`, `OPEN_UNCONFIRMED`, `SELECTION_UNAVAILABLE`, `CANCELLED`, `HISTORY_BASIS_UNBOUND`, `HISTORY_UNAVAILABLE`, `IDENTITY_INIT_NOT_FRESH`, `OWNER_IDENTITY_CHANGED`, `FIRST_SAVE_TARGET_REQUIRED`, `LINK_UNSUPPORTED`, `LINK_UNAVAILABLE`.

`effects`는 실제 수행 단계만 기록한다. `native_save`, `native_launch`, `native_load`, `reader_read`, `native_view_evaluation`과 `provider_calls`, `solver_submissions`, `mesh_submissions`, `new_analysis_apply`를 구분한다. 측정하지 않은 횟수는 null/NOT_OBSERVED이며 0으로 꾸미지 않는다. 파일 무결성 통과·native 열린 상태·공학 승인을 한 status에 합치지 않는다.

## 12. root·Pre·Post의 병렬 파일 책임

### 12.1 세 개의 완결 인도 묶음

| 묶음 | 작성 책임 | 전용 소스/핵심 인도 | 사용자 종료조건 |
|---|---|---|---|
| **N0 공통 저장 참조·복사·opener 연결** | root가 공통 계약/통합 최종 소유. Sol-N0가 전용 helper 작성 | contract/inputs/portable helper, 독립 open ID·첫 저장 예약/head, replacement 검증·DeclaredResearchLink, history basis 보존/mapping | mixed/native-only의 exact 참조·복사/재확인과 두 intent identity·첫 저장·HISTORY_ONLY가 같은 계약. N2 basis를 손실 없이 재복사 |
| **N1 FreeCAD 작업 사본** | Sol-Pre | Pre adapter·metadata-only 초기화·기존 Project/native_cad 최소 hunk·editable XLink 예제 | 원 dirty 창과 saved/working 별도 창 동시 유지, 초기화 recompute/사용자 Undo ID복귀0, 첫 저장 분리와 cold/recopy 완료 |
| **N2 ParaView 분석 사본** | Sol-Post | 단일 codec, graph+bindings/source-basis helper, Workspace describe/verify/부분 Save, Post owner/restore | source→retained A→B 이력별 정확 비교·cursor 차이 표시·부분 Save·재복사, 원 dirty 창과 saved import의 독립 첫 저장 완료 |

N0를 새 프로젝트 전체 엔진으로 키우지 않는다. N1/N2가 각각 Core wire/registration/portable manifest를 별도로 정의하지 않는다. 한 사람이 모든 native 작업을 끝낼 때까지 타 묶음의 구현을 중단하지 않는다.

### 12.2 공유 파일 수정 소유권

| 공유 파일/기존 함수 | root가 반영할 변경 | 다른 소유자의 작성 경계 |
|---|---|---|
| `caelab/native_inputs.py::_register_set/register_native_input`, `NATIVE_EXTENSIONS` | snapshot sidecar 최종 발행 hook, native_post_project dispatch | Post codec 재사용. frozen/data/FN05 경계 광역 수정 금지 |
| `caelab/workbench.py::input_path/native_input/document_command` | new input kind 검증, trusted receipt/binding, public wrappers | current 연구팀 hooks 덮어쓰기 금지 |
| `caelab/connection_graph_refs.py` | native form/path adapter와 native-first resolution | 연구팀 typed response/source closure 추가와 한 번 통합 |
| `connection_graph.py/native.py` | saved node 분리, native/HISTORY_ONLY resolver | live report와 saved proof 혼합 금지 |
| `portable_project.py::_selections/inspect_copy/_Fork.reference/_Fork.write/verify_project/open_project` | native union 분리, /1·/2 dispatch, pure native-only context | 연구 existing projections/retention 불변 |
| `caelab/desktop_links.py` | saved-command witness·current native head 연결의 좁은 wrapper | `submit_frozen` execution 원칙 유지, copy에서 호출 금지 |
| `caelab/native_commands.py::기존 register/event/submit·status` | open/save의 trusted binding 주입과 완료 대조만. duplicate-owner·session ID 집합 guard 유지 | guard 완화·원 owner ID takeover·새 scheduler 금지 |
| `apps/research/desktop.py::_pre/_post/open_evidence_reference/open_saved_reference` | native kind를 generic knowledge/document branch보다 먼저 처리; native-only trusted local context | measurement/report/curve origin·launch claim 보호 |
| `apps/desktop_post/workspace.py::source_stamps/_verify_record/describe/prepare_save` | N2가 graph+bindings helper/retained-vs-current 비교·부분 Save hunk 작성, root가 한 번 적용 | source_stamps/새 Apply는 actual 유지. N0는 durable basis/member mapping 소유. graph/core/hash 수정으로 mismatch를 숨기지 않음 |
| Study/Expert/Report/Numerical의 기존 reference validator | §9의 명시 provenance-native union만 | sourcegrant/연구팀 v2/실행 model_source 의미 변경 금지 |

Pre 작성 hunk는 `projects.Project.save/open/attach_opened`, `remember_open`, metadata-only import 초기화·native save UI/bridge descriptor 및 `native_cad` 허용 relocation 검증이다. `_transaction` 전체를 고쳐 recompute/Undo를 제거하지 않고 import만 별도 좁은 경계로 처리한다. Post 작성 hunk는 `Owner.save_project/start`, `Workspace.prepare_save/_retained_reader_binding/_verify_record/describe/source_stamps의 호출부/repair_source`, `external.save_project/restore_workspace/verify_readers`, `source_repair`와 `startup/commands`의 정확한 연결이다. 소유한 hunk를 root가 현재 WIP와 대조하여 게시한다. 공유 전체 파일을 과거 기준으로 교체하지 않는다.

첨부에서 본문을 제공하지 않은 Pre 메뉴 등록/저장 dispatcher, 부분 portable constructor, 기존 source_change.content_set 세부 구현은 **기존 symbol을 호출할 연결 위치**이며 전체 구현 검토로 계산하지 않는다. 이번 계약은 함수의 입력/출력을 확정한다. 구현자는 변경할 실제 파일을 읽고 기존 API 동작을 보존해야 하며 미확인 함수의 반환값을 추정해 mock으로 통과시키지 않는다.

### 12.3 선행관계

작성은 세 묶음이 병렬이다. N0의 §3/§11 자료형과 /2 format만 먼저 공통으로 둔다. N1은 실제 `.caepre` 저장·열기와 local selector를, N2는 pure XML closure와 실제 saved Post restore를 각각 진행한다.

검증 통합 순서는 `N0 contract + N1/N2 source inspection → pure copy/original·derived 검증 → 각 native cold round trip → mixed 연구 참조 → 두 번째 recopy`다. 이것은 다른 제품 개발이나 연구팀 A/B/C/D를 멈추라는 지시가 아니다. 종료 plugin·새 solver campaign·유료 모델 호출은 선행조건이 아니다.

Astra는 R1의 bindings-first·current cursor·history별 basis·재복사, R2의 독립 live ID·첫 Save/head·원 dirty 창 보호 및 다음 핵심을 독립 검토한다: live descriptor의 saved proof 오인, missing child의 현재 bytes를 과거 사실로 소급, snapshot/derived 해시 혼동, actual reader closure 누락, 원문 경로 search/replace, partial 성공 과장, 원 controller 권한 복제, current/native 읽기 상태와 새 실행 혼동.

## 13. 사용자 완료 조건과 최소 실행 증거

### 13.1 시험층을 분리한다

| 층 | 수행할 확인 | 그 결과로 주장할 수 없는 것 |
|---|---|---|
| pure contract/file IO | refs·registration·XML/XLink closure·byte copy·transaction·head·typed mapping | FreeCAD/ParaView GUI 정상 동작 |
| controlled native boundary | 실제 dispatcher/storage와 명시 stub native 결과를 이용한 실패/취소/유실응답 | 실제 saveCopy/LoadState/selection 성공 |
| 실제 native 공개 예제 | 설치된 Windows FreeCAD/ParaView, 편집 가능한 공개 문서, source 없는 cold/recopy | 모든 reader·모든 CAD 기능·회사 제품 공학 적합성 |
| 실제 혼합 사용자 흐름 | native+선택 Study/Report/Plan/실제 retained result 연결 | 새 solver campaign 또는 연구팀 전체 수용 |

검사 기록에는 source identity, 검사한 OS/실제 app 버전, actual process ID와 소유 범위, source/copy1 접근 차단 방법, original/derived 검증 결과, exact 선택 readback, 수행·미수행 effects, 실패/시간초과/NOT_RUN을 남긴다. artifact 파일 검사만 통과했다고 native 수용 수치에 합산하지 않는다.

### 13.2 공통·Pre·Post 핵심 사례

| ID | 사례 | 통과 조건 |
|---|---|---|
| NP01 | live native descriptor만 있고 저장/등록 없음 | copy saved 선택 불가. 정상 native 편집은 가능, 명시 Save 후에는 선택 가능 |
| NP02 | 같은 PVSM·다른 project/history 또는 source 선언 | 서로 다른 snapshot. 같은 saved native_revision으로 합치지 않음 |
| NP03 | same filename/Label·다른 owner/revision/bytes | exact ref 충돌/변경 검출. source exact ID와 materialization live ID 구별; 이름으로 activate·repair하지 않음 |
| NP04 | .caepre raw archive와 member 보존 | 모든 original bytes 동일. native_copy_sha만 있는 저장 전 bytes를 복원했다고 주장0 |
| NP05 | raw FCStd + 외부 XLink + 반복 occurrence | file dedupe하되 occurrence/target 유지. 다른 doc/face를 선택하지 않음 |
| NP06 | XLink relocation | 허용 file attribute 외 XML 의미·다른 ZIP member 동일. 원 archive overwrite0 |
| NP07 | doc/task/linked child 미저장·busy·closed | 명시 저장/마지막 저장본/취소 각각의 효과가 맞음. 다른 열린 문서 상태 보존 |
| NP08 | preview 자세 후 Save | 기존 설계 자세 복원과 원 pose 적용 구별. 이동 때문에 새 운동/메시/solver0 |
| NP09 | raw FCStd 동일 basename·cross-doc expression | ambiguity를 자동 rename success로 숨기지 않음. 실제 관리 저장 경로로 해결 가능 |
| NP10 | PVD 시계열·중복 timestep/group/part | 모든 frame pin 포함, 원 ordinal/시간/part 유지, 하나의 frame 변경도 검출 |
| NP11 | .pvtu Piece Source·VTM 계층 | child 누락을 COMPLETE로 통과시키지 않음. format codec별 graph와 실제 native 지원 구분 |
| NP12 | raw appended VTU 등 binary leaf | reader data bytes 그대로. 일반 ET 재직렬화·값 변경0 |
| NP13 | duplicate/casefold member, root escape, cycle, oversized metadata | publication 전 차단. 정상 공유 child 참조는 허용 |
| NP14 | reader name/type/slot 순서·property가 바뀜 | preflight 또는 readback에서 차단. source 이름 하나 일치로 PASS0 |
| NP15 | actual retained_reader A와 latest result_files가 다른 history, A를 소비한 B | 두 파일 세트/정확한 A revision을 각각 보존. B bindings의 FileName과 graph를 같은 검증 slots로 비교; 현재 cursor로 대체0 |
| NP16 | native field sidecar/dynamic full closure | 기존 validators와 full byte 검사. 현재 선택 frame만 검증해 전체 PASS0 |
| NP17 | healthy A + missing B + retained/누락 history | 건전한 값·view 유지, unavailable history 원 recipe/graph/bindings/pins와 Undo/redo 보존. 새 partial Save·recopy 가능, summary를 검증값으로 제공0 |
| NP18 | 같은 내용 registered replacement로 source/retained reader 위치 수리 | public 대응→N0 검증→private map 한 경로. graph+bindings·metadata 검증 후 한 commit, 실패면 reader/document/Undo/selection 보존 rollback |
| NP19 | PVD 한 frame·metadata·relative names 변경 | CONTENT_CHANGED. 새 결과 추가/새 revision만 가능, 위치 수리로 세탁0 |
| NP20 | unknown reader/programmatic proxy/remote path | 원 state 보존·기능 단위 차단, silent fallback/open success0 |
| NP21 | source 파일이 inspection/복사 중 바뀜 | parse 전후·복사 후 전체 재검사 실패, 정상 receipt/final manifest 발행0 |
| NP22 | 저장/등록/복사 응답 유실·동일 command 반복 | 동일 source/ref/destination 반환, native Save·새 job·새 사본 중복0 |
| NP23 | 목적지 존재·disk full·취소·rename 실패 | 원본/이전 정상 사본 보존, partial staging 표시, 허위 완료0 |
| NP24 | staging rename 뒤·copy 폴더 다시 이동 | 실행용 paths는 현재 최종 위치에서 파생. 옛 staging/source fallback0 |
| NP25 | copy1에서 Save만 한 B0와 새 Apply한 B1을 함께 저장 | B0는 원 basis, B1은 copy1 actual basis. 두 history core/digest 불변 및 각 current head 검증, copy2에 직접 1회 투영 |
| NP26 | 원 dirty 창 + saved import + 별도 working 창이 같은 service에 있음 | 세 live ID/source·target 구별, duplicate-owner guard 유지. 원 편집/Undo 불변, saved 첫 Save는 새 K만 갱신; 취소는 생성·저장0 |
| NP27 | mixed Study/Expert/Report/Plan의 과거 native 근거 열기 | 원 dirty 창 대신 exact snapshot의 독립 import. source ref/FN05/Report A 불변. 새 first-save ref/target은 별개이며 원 링크 HISTORY_ONLY |
| NP28 | copied 원 job/session/PID/권한 | HISTORY_ONLY 읽기, 원 lookup/harvest/retry/자동실행0. 새 local 명시 실행 경로는 정상 유지 |
| NP29 | native-only, service/AI/MCP 없음 | 파일 열기·편집·저장·복사·재열기 가능, Workbench/JobManager 자동생성0 |
| NP30 | source 없는 cold1·편집·Save·recopy, source/copy1 없는 cold2 | Pre와 Post 모두 실제 추가 편집·선택 가능. inherited B0/new B1 basis와 새 target 저장 포인터를 이전 경로 lookup 없이 복원 |
| NP31 | 한글/공백/긴 경로, narrow window, Ctrl+S/Cancel | 실제 native 의미·buffer·focus 유지, hash/JSON 입력을 요구하지 않음 |
| NP32 | 실제 process 종료 실패/불명확 | OPEN_UNCONFIRMED/cleanup 미확인 사실 유지, PID 이름만 보고 타 process 종료0 |
| NP33 | /1 옛 사본과 /2 native 사본 | /1 정상 유지, /2 전체 native 검사. 구형 reader가 /2를 조용히 무시하지 않음 |
| NP34 | partial 선언 vs 정상 inventory 유실/변조 | 전자만 명시 partial 보관 가능, 후자는 exact repair 전 BLOCKED |
| NP35 | graph와 bindings FileName의 path-only 변경 / 제3 경로·배열·port·type·인자 변경 | 같은 history/slot/current destination·전체 pins일 때만 통과. 다른 변경은 실패; graph/bindings/core 원 hash를 rewrite하지 않음 |
| NP36 | raw PVSM에서 관리 프로젝트로 저장 | 기존 reader 중복 생성0, 원 PVSM 불변, 실제 새 native Save 뒤에만 complete selection 가능 |
| NP37 | exact dynamic time이 선언 범위 밖 | 첫 frame fallback으로 선택 성공 표시0; 명시 selection 제외 열기 또는 정확 자료 복구 가능 |
| NP38 | source→retained reader A0→B0; 이동·Save·새 Apply B1·재복사, A cursor를 A1로 이동 | 이동만일 때 B0/B1 검증·current_inputs_differ=false. cursor A1에서는 B0 과거 검증 유지/current differ=true. 양쪽 history basis로 cold2·Undo/Redo, 원 A0로 cursor 몰래 변경0 |
| NP39 | Pre·Post 각각 원 dirty 창의 과거 saved를 동시에 열고 첫 Save/취소/응답 유실 | open ID/owner ID 안정, source exact 유지. Cancel 후 import 편집 보존. 새 K 첫 저장·publish 재확인·recopy와 원 창의 후속 Save가 서로 다른 head, 중복 launch/Save0 |
| NP40 | 두 승인 root의 replacement 및 위조 receipt/path/null expected pin | replacements keyword만 수용. private codec에 같은 verified map 전달. 동일 세트 정상, 제3 파일/권한 밖/호출자 expected 위조 차단; null expected로 동일 복구 승인0 |
| NP41 | 새 Pre import identity 초기화→치수/조건 편집→Undo/Redo→Save | metadata 허용 diff만, adapter 추가 recompute/save0, 원 geometry 검사 유지. 초기화가 user Undo에 없고 original ID 복귀0, 원창 Undo 불변 |
| NP42 | bundle 없는 declared history와 healthy sibling을 부분 Save→recopy→cold2 | unavailable 원 기록/expected pins/누락 계속 보존, summary는 미검증. 정상 sibling 저장 성공. 기록 없는 bundle 제거·타입 변경·immutable 유실·중간 추가 유실은 저장/발행 차단 |
| NP43 | native_links=[] 또는 exact research/native/result·원 job의 명시 링크 | [] 정상, 고정 source site/target union만 수집. 지정 files/원 job state·origin 불변. cold/recopy 원 controller lookup·harvest·retry0, 현재 동명 job로 대체0 |

NP11의 native reader 일부가 현재 target에 없다면 그 type은 NOT_RUN/UNSUPPORTED로 남긴다. 다만 **지정된 필수 정상 Pre/Post 예제와 NP10·NP15·NP17·NP18·NP25·NP27·NP29·NP30·NP38–43을 수행하지 않고 CB07/08 전체 완료를 선언하지 않는다.** codec 검사에서 지원하지 못한 dependency가 있는 사용자 project를 성공으로 누락시키는 것도 통과가 아니다.

### 13.3 최소 공개 native 예제 두 개

**Pre 공개 예제.** 기존 FreeCAD 기능만으로 root assembly + 외부 editable child 2개 + 같은 child의 두 Link occurrence + 최소 한 FEM 조건을 저장한다. 한 child/parent의 native property를 사용자가 편집할 수 있어야 한다. 기존 source hash/selected object/조건 값을 기록하고 save→copy→원 root 차단→cold1 open→선택/치수 또는 조건 변경→Undo/Redo→native Save→recopy→copy1 차단→cold2 open을 수행한다. 원 shape/mesh/하중 snapshot은 불변이고, 새 편집 값은 새 저장본에만 나타난다. 별도 새 solver campaign 없이, 같은 예제에서 **원 dirty 창을 계속 둔 채 과거 저장본을 saved intent로 열기 → identity-only 초기화 확인 → 편집/Undo → 첫 Save 취소 → 다시 명시 새 target Save → 재복사**를 수행한다. 동일 command 유실응답 재확인과 원 창의 별도 후속 Save도 확인한다. 새 FE solver 실행은 필요 없다.

**Post 공개 예제.** 이미 보존한 공개 VTU/PVD 또는 명시 합성 VTK source 2개를 사용한다. source A/B는 basename 충돌과 구별되는 값을 포함한다. 하나는 상대 PVD time series, 하나는 기존 retained 분석 결과/history를 포함한다. source/filter·array/component·time·camera·view/layout을 지정하고 저장한다. copy→원 root 차단→cold1 restore/readback→filter/표시 또는 기존 분석 draft 편집→명시 Apply가 필요한 경우 그 단계만 수행→Undo/Redo→Save→recopy→copy1 차단→cold2를 확인한다. 같은 예제에 **원 source→보존 결과 reader A0→그 A0를 입력으로 삼은 B0**를 만든다. B0가 일반 graph 검증을 거치는 경우와 retained-only 표시인 경우를 따로 확인한다. copy1 Save만으로 원 bindings/graph는 바뀌지 않고, 명시 새 Apply한 B1은 copy1의 actual basis를 가진다. A cursor를 A1로 옮겼을 때 과거 B0 검증과 현재 입력 다름 표시가 서로 맞는지 확인한다. cold2는 B0/B1 basis를 직접 검증하고 제3 경로/성분/port/필터 변경을 거절해야 한다.

같은 Post 프로젝트로 원 dirty 창과 saved import의 첫 Save/Cancel·새 target/head·원창 후속 Save 분리를 확인한다. 추가 branch에서는 등록된 같은 bytes repair, changed frame 거절, declared missing history와 정상 형제의 부분 Save/재복사를 수행한다. 원 root/copy1의 파일로 basis를 찾아가는 경로는 counter/차단으로 확인한다.

합성 데이터는 synthetic으로 표시한다. 위 Post 예제를 실제 solver가 생성한 결과라고 주장하지 않는다. 기존 FreeCAD FEM→공식 VTU→ParaView 결과를 소비하는 혼합 증거가 이미 있으면 그대로 재사용하고 전체 물리 campaign을 다시 실행하지 않는다.

### 13.4 전체 인도 종료판정

CB07 완료는 native 모델이 사본에서 실제 editable하고 재저장/재복사되는 것이다. `.caepre`가 압축 해제되거나 그림이 보이는 것만으로 끝내지 않는다.

CB08 완료는 saved pipeline/reader/history와 현재 선택·표시를 구별해 실제 native에서 재개하고, retained A를 입력으로 쓰는 B의 bindings/graph·history별 basis·current cursor 의미와 부분 Save까지 보존하며 동일 내용 repair·새 결과 추가·재저장/재복사가 되는 것이다. PVSM 파일 하나의 존재나 `LoadState`가 예외 없이 끝난 것만으로 끝내지 않는다.

합동 완료는 원 dirty 창과 과거 saved import가 동시에 존재해도 source identity·현지 owner·첫 Save target이 충돌하지 않고 한 native saved selection이 연결된 연구 도구에서도 같은 원본을 가리키며, source/controller 없는 copy에서 원 근거 읽기와 현재 편집·새 명시 실행의 책임이 분리되는 것이다. 수치 성공·모델/mesh 표시·저장 hash 통과를 공학 release로 변경하지 않는다.

## 14. 중요한 대안과 선택 이유

| 대안 | 판단 |
|---|---|
| 공통 `NativeDocuments` owner·일반 프로젝트 DB 신설 | 거부. native owner가 이미 edit/Undo/save를 소유한다. input receipt + 작은 current 포인터면 충분하다. |
| live descriptor를 saved snapshot으로 복사 | 거부. session identity와 실제 파일 증거가 다르다. |
| Post `workspace_sha256`만 참조 | 거부. project metadata/history/reader closure가 빠진다. |
| `.caepre`/PVSM 저장 기능 자체 교체 | 거부. 기존 native save와 실패 경계를 보존하고 snapshot 연결만 추가한다. |
| 모든 native를 연구 owner SUPPORTED에 추가 | 거부. 연구 revision/owner open 계약을 native에 강제한다. tagged selection과 별도 native manifest branch를 선택한다. |
| /1에 알 수 없는 native 필드만 추가 | 거부. old reader가 검사를 생략할 수 있다. native 포함 /2를 사용한다. |
| source folder 전체 ZIP | 거부. 미선택/실행환경 포함, 실제 dependency/branch 의미 상실. |
| basename matching / arbitrary JSON·XML 문자열 replace | 거부. 동일명 다른 결과·time/branch·물리 참조가 바뀔 수 있다. |
| 매 사본에서 모든 파일명 hash화 | 기본안 아님. 원 relative layout을 유지하면 대부분 container rewrite가 필요 없다. namespace만 분리한다. |
| PV `LoadState(data_directory=...)` 자동 검색에만 의존 | 기본안 아님. 검증된 exact reader 슬롯 mapping을 먼저 만든다. native file chooser/API는 그 검증 결과를 소비한다. |
| 저장·검사 시 전체 remesh/solver·시간시리즈 분석 재실행 | 거부. 이동의 증거가 아니라 새로운 계산이다. 필요한 실제 편집/Apply는 명시 동작으로 분리한다. |
| 모든 미지원 reader를 영구 일괄 거절 | 아님. supported codec/type 조합부터 정상 사용을 완결하고 branch 단위 상태·명시 반입/새 저장 경로를 제공한다. 알려지지 않은 reader를 성공으로 취급하지 않는다. |
| 현재 ParaView session에 무조건 LoadState | 거부. 새 process+독립 owner ID가 기본. working exact target만 제한적으로 activate, saved는 같은 command만 재확인한다. |
| graph만 투영하거나 source_stamps에서 FileName 전역 삭제 | 거부. retained A를 쓰는 B의 bindings-first 검증과 current cursor 의미가 닫히지 않는다. history별 두 비교만 투영한다. |
| saved intent에서 원 ID 재사용 / duplicate guard 완화 | 거부. 원 dirty 창과 충돌한다. 독립 materialization ID를 첫 저장의 새 target에서도 유지한다. |
| 연구팀·종료 plugin 완료까지 native 개발 대기 | 거부. 인터페이스와 소유권을 분리해 병렬 개발한다. |

## 15. 추가 불변식과 구현 시 선택이 남지 않도록 정한 세부 사항

### 15.1 declared native metadata

`DeclaredMetadataBinding`은 `{kind, declaration_member, declaration_sha256, data_member_ids, source_registration_origin}`이다. kind는 현재 사용하는 `dynamic_locations/contact_inspection/shell_inspection/beam_inspection/curve` 중 하나로 제한한다. 공통 unknown metadata를 자동 해석하지 않는다.

Post 담당은 기존 `dynamic_api.verify_saved_source/load`, `contact_api.load`, `shell_api.load`, `beam_api.validate_metadata`, `post_curves.load_curve`의 반환 paths와 declaration을 exact registered member에 결속한다. 원 sidecar bytes와 original registration_origin은 history다. 현지 path와 input ID를 바꾸어도 의미 metadata를 다른 reader/filter에 상속하지 않는다. 기존 validator에 필요한 current file locator는 trusted member map으로 공급하고 source validator가 실패하면 임의 metadata hash 재작성으로 통과시키지 않는다.

단순 source frame bytes 외에 location/raw solver companion이 있는 dynamic source는 **full closure verification**을 registration/copy publication 관문에서 수행한다. 현지 정상 값 읽기의 기존 selected-frame 최적화와 전체 archive 검증을 섞지 않는다.

### 15.2 snapshot과 receipt 순환 방지

`native-project.json` 자체는 `members`/saved_basis 안에 넣지 않는다. source file set과 원 native manifest의 pin으로 saved_basis/saved_revision을 만든 뒤 snapshot record의 자체 hash를 계산하고, 마지막으로 이 sidecar의 file hash를 input.json에 기록한다. 따라서 self hash 또는 receipt ID를 재귀 hash하는 순환은 없다.

`.caepre` archive identity와 내부 member identity는 각각 검증한다. archive file bytes를 복사할 때 내부 파일을 다시 ZIP으로 만들어 원 archive와 같다고 주장하지 않는다. derived project를 만들 때만 기존 `publish_project`를 쓸 수 있고 그것은 별도 derived artifact다.

### 15.3 사본의 원본 보존과 실행용 환경 비활성화

raw source 기록의 원 session/host 문자열은 출처 설명일 수 있으나 active authentication이 아니다. operational runtime file(credential/token/provider profile/command queue/launch config)은 수집하지 않는다. 원 project 안의 nonsecret path 또는 origin field를 보존하는 것과 그 값을 따라 파일/서비스를 열게 하는 것을 분리한다.

`prepare_open`은 원 project의 다음 launch 필드를 current project에 복제하지 않는다: `service_url`, `desktop_python`, `repo_root`, 원 active `origin_job_id`와 `origin_research_source`. 원값은 raw archive와 source_links에만 남는다. 현재 연결을 원할 때 같은 local target의 검증된 연구 mapping으로 새 launch environment를 작성한다. global environment에서 상속된 `CAE_POST_MEASUREMENT/CAE_POST_REPORT_ORIGIN/CAELAB_ORIGIN_JOB_ID`도 기존 _post처럼 먼저 제거한다.

### 15.4 로컬 등록 ID와 metadata source identity

local input ID는 copy에서 새로 생성할 수 있다. 그러나 같은 source snapshot의 `source_document_id/saved_revision/snapshot_sha256`는 바꾸지 않는다. working document ID는 새 ID이고 native save를 완료했을 때만 그 새 ID의 native saved reference가 생긴다. 따라서 `NativeTarget.source.document_id != NativeTarget.working_document_id`가 정상이다.

Project.open의 import identity 변경은 **§5.4의 attach 전 metadata-only 초기화**다. `_transaction/recompute`·사용자 Undo queue와 구별하며 XML `file` 경로 relocation과 별도 허용 diff로 기록한다. 첫 저장 target 승격 때는 ID를 다시 바꾸지 않는다. 물리 bound source로 쓰이는 원 모델/관측/source hash를 working ID에 맞추려고 재작성하지 않는다. 새로운 모델 binding은 기존 Pre의 명시 재검사/Apply/freeze가 맡는다.

### 15.5 검사 실패가 일반 native 파일 사용을 막지 않는다

unsupported file-bearing addon/reader/pipeline은 자동 이동·managed source proof의 범위 밖이라는 뜻이다. 사용자는 기존 native Open/Save로 그 파일을 계속 사용할 수 있다. 다만 그 ordinary open을 general portable 정상 완료라고 계산하지 않는다. 오류 화면에는 해당 reader/feature와 필요한 명시 복구 동작을 표시하고 여러 정상 source까지 이유 없이 삭제하지 않는다.

### 15.6 발행/재열기 검증의 원자 경계

core의 publication은 filesystem atomic rename 및 기존 `_publish_json/save_json/copy_verified` 패턴을 따른다. native save+registration+head는 하나의 분산 transaction이라고 가장하지 않는다. 각각 durable milestone을 남기고 사용자에게 마지막으로 확정된 단계와 실패 단계를 구별해 반환한다. 같은 command recovery는 확정된 결과를 재사용하고 native 작업을 반복하지 않는다.

독립 native 작업 중 원 FCStd/PVSM가 외부 writer에 의해 바뀔 수 있다. Lab lock만 믿지 않고 bytes/stat의 사후 검증을 유지한다. Windows ctime을 휴대 가능한 파일 identity로 새로 도입하지 않는다. 기존 `_identity`의 device/inode/size/mtime 및 bytes 검증을 사용하고 원/현지 파일 identity가 같아야 한다고 요구하지 않는다.

### 15.7 버전과 실행 가능성

첫 native 수용의 기준 runtime은 현재 제품이 지정한 FreeCAD 1.1.4 및 ParaView 6.2다. 이는 이 문서가 실제 설치본을 실행했다는 뜻이 아니다. `producer.version`은 authenticated save 보고 또는 원 저장 metadata에서 확인한 값만 채우고, raw 파일에서 알 수 없으면 null/unknown이다. 프로그램명·파일명·latest 매뉴얼로 버전을 만들어 넣지 않는다.

읽기/복사 integrity와 target readiness는 별도다. 다른 버전 또는 없는 addon/reader이면 원 archive·과거 결과 읽기는 유지하고, 해당 native open capability는 `NOT_VERIFIED/UNAVAILABLE`로 표시한다. 문서 schema 불일치·원 proxy type 부재는 native 복원을 거절한다. 실제 current native가 같은 typed API/파일 형식과 round-trip 검사를 통과한 경우에만 호환 capability를 등록한다. 최신 설치·패키지 다운로드를 자동 요청하지 않는다.

### 15.8 여러 승인 root·등록 실패·원 경로 해석

여러 root의 파일을 한 `_register_set(root,...)`에 그대로 넣으면 `relative_to(root)`가 실패하므로 그런 호출 계약으로 넘기지 않는다. 추가 `register_saved(..., replacements=())`는 `verify_replacements`로 확인한 registered replacement의 파일들을 **하나의 owner-private admission staging root**에 기존 copy_verified로 먼저 배치한다. namespace는 `(등록 input ID, 그 세트의 relative)`로 고정하고 파일명 충돌을 basename으로 합치지 않는다. 원 saved bytes는 그대로이며 원 absolute 참조의 해석은 snapshot의 `logical_origins/edges`가 담당한다. staging metadata가 자의적으로 파일 목록을 추가할 수 없다.

이때 saved_basis의 member 이름은 최초 원 세트의 논리 이름이고, input receipt의 `files[].relative`도 그 확정된 namespace다. 원 XML이 old absolute path를 포함해도 inspection은 old path를 따라 디스크를 열지 않고 N0가 private `_replacements`로 전달한 검증된 edge/member pin에 대조한다. `post_project_files`와 그 하위 inspect_dataset, Pre pre_snapshot_files가 동일 verified map을 소비한다. public replacements를 native callback의 caller path/receipt로 재해석하지 않는다. `Project.open/working_copy`의 private binding은 이 대응표를 사용한다. 원 source 파일 세트와 관계없는 같은 이름의 파일은 fallback이 아니다.

상대 경로가 바뀐 local input.json, admission 명령 기록, open ticket, head 갱신 receipt는 새 사본의 현지 관리 기록이다. 최초 saved_basis와 raw original native 파일은 바뀌지 않는다. native_save 실패 후 남은 recovered bytes는 사용자 명시 복구로만 등록하며 이전 원 revision이나 명령의 성공을 소급 생성하지 않는다.

## 16. 출처·보충 조회와 산출물 상태

### 16.1 첨부 기준

- [C-REQUEST] `correction-request(1).md` 전문. 이번 최우선 교정·main/WIP 보호·전체 대체본 요구.
- [C-REVIEW] `REVIEW(1).md` 전문. R1/R2 관련 소스 대조와 세 동반 명세 권고. 실제 native 실행 보고가 아님.
- [R] `request(20261015-180822).md` 전문. 계속 유효한 제품 방향·기존 통합 성과·CB07/08·역할·완료 조건.
- [S] `source-bundle.md` 전문. packet의 file manifest/blob ID·source line numbering·omission register를 기준으로 한다. 전체 저장소 또는 사용자 native 파일 검증이 아니다.

| 참조 | source-bundle의 원 소스 파일·줄 범위 |
|---|---|
| S-PRE | `apps/desktop_pre/projects.py` 1–387; packet의 여러 발췌를 합쳐 저장·dependency·attach/open 경로 확인. `bridge.py` 158–210 |
| S-CAD | `caelab/native_cad.py` 1–212. remaining working_copy는 아래 A-CAD로 보충 |
| S-INPUT | `caelab/native_inputs.py` 1–82, 130–220 |
| S-WB | `caelab/workbench.py` 165–197, 211–270, 437–569 |
| S-POST | `desktop_post/bridge.py` 1–237, 491–514; `external.py` 1–185, 563–711, 729–844 |
| S-WORK | `desktop_post/workspace.py` 1–437의 제공 구간, 486–498, 1165–1206, 1254–1268 |
| S-REPAIR | `desktop_post/source_repair.py` 1–335 및 startup 1–61 |
| S-CMD | `desktop_post/commands.py` 1–17, 223–276 |
| S-GRAPH | `connection_graph_refs.py` 1–109; native.py 1–43; graph.py 1–36, 286–413 |
| S-PORT | `portable_project.py` 1–185, 804–928 |
| S-PLAN | packet의 PRODUCT_PLAN / PRODUCT_UI_MCP_PLAN / PREPOST_APP_SPEC / PREPOST_REUSE 발췌 |

본문 링크는 위 동일 commit의 파일에 연결한다. 원 excerpt가 생략한 unrelated 기능을 읽은 것으로 확대하지 않는다.

### 16.2 동일 commit의 제한된 보충 조회

직전 -01 설계가 기록한 추가 조회 범위는 다음과 같다. 이번 -02 교정에서는 이를 재실행하지 않았고, 아래 이력을 현재 main/WIP 확인으로 확대하지 않는다. live main이나 local WIP가 아니라 모두 `8bd6bd74c2f1932608b1c6c96296216abb6383a5`다.

| 참조 | 조회 범위 | 확인 목적 |
|---|---|---|
| A-CAD | `native_cad.py` 201–끝(요청 330까지) | registered working_copy·original_locations·basename collision 처리 |
| A-FORK | `portable_project.py` 425–670 | 실제 `_Fork` typed projection/write, original/current 분리 접합 |
| A-WB | `workbench.py` 70–164 | native는 research document_open 대상이 아님, 기존 owners/desktop 구성 |
| A-LINK | `desktop_links.py` 1–225 | submit_frozen의 현재 실행 경계, retained job/navigation |
| A-CMD | `native_commands.py` 1–205 | native kind·현재 host/session·APPLYING/timeout·completion 경계 |
| A-DESKTOP | `apps/research/desktop.py` 1–240, 455–795 | 현재 _pre/_post/cae_prep/startup·native receipt와 실제 launch/reopen 경로 |
| A-ANALYSIS | `apps/desktop_post/analysis.py` 1–210, 270–525 | graph_signature의 file property 포함, retained fingerprint·native reader update와 소유 cleanup 경계 |

직전 설계에서는 파일 검색 위치 확인용 `apps`와 `apps/research` tree 목록도 조회했다. 그것은 각 파일 본문 검토가 아니다. 위 이외의 launcher/module 전체 검토, Windows 실행, 새 source patch 작성은 하지 않았다.

### 16.3 이전 설계의 외부 1차 자료 — 이번에 새 조회하지 않음

[W-PV] ParaView 6.2.0 Users Guide, Saving Results. native Save Data와 Save State의 차이, PVSM 파일 위치 선택·LoadState가 현재 session에 영향을 주는 점을 확인했다. 제품의 exact receipt·새 process·부분 복구 정책은 이 설계의 결정이지 매뉴얼이 제공하는 complete portable 보증이 아니다.

[W-VTK] VTK 공식 XML file formats 문서. parallel `Piece@Source`와 serial/appended data 구조를 확인했다. 기존 packet의 `file`-only traversal을 그대로 complete closure로 삼지 않은 근거다.

[W-READER] ParaView 공식 Python 6.0 reader 목록 및 앞서 조회한 5.12 XMLPartitionedUnstructuredGridReader 문서. §6.2의 표는 구현할 native type 대조 목록이다. 다른 버전의 API 페이지 존재를 현재 설치 6.2 native 수용으로 계산하지 않는다. exact type/property/slot cardinality는 실제 source PVSM·target native readback으로 확인해야 한다.

### 16.4 이 인도의 상태

산출물은 -01을 대체하는 이 **전체 편집 가능한 교정 설계 MD 한 개**다. product.patch 또는 제품 구현 ZIP이 아니다. 파일 저장·UTF-8 재읽기·문서 참조/코드 fence·필수 계약 포함 여부를 확인한다. 위 NP01–43은 구현 후 수행할 계약이며 이 문서 작성으로 PASS됐다는 뜻이 아니다. 실제 제품 코드·native·Windows·solver·provider 검사를 실행하지 않았다.

추가 사용자 승인이 필요한 제품 방향은 만들지 않았다. 명시 Save/포함/repair/native Apply·실행은 제품을 사용할 때 각 사용자가 하는 조작이다. root는 기존 제품 통합을 계속하며 이 문서의 공통 변경만 N0/N1/N2와 연구팀의 shared hunk에 일관되게 반영한다.

[C-REQUEST]: <correction-request(1).md>
[C-REVIEW]: <REVIEW(1).md>
[R]: request(20261015-180822).md
[S]: source-bundle.md
[S-PRE]: https://github.com/pikachu444/autonomous-cae-lab/blob/8bd6bd74c2f1932608b1c6c96296216abb6383a5/apps/desktop_pre/projects.py
[S-CAD]: https://github.com/pikachu444/autonomous-cae-lab/blob/8bd6bd74c2f1932608b1c6c96296216abb6383a5/caelab/native_cad.py
[S-INPUT]: https://github.com/pikachu444/autonomous-cae-lab/blob/8bd6bd74c2f1932608b1c6c96296216abb6383a5/caelab/native_inputs.py
[S-WB]: https://github.com/pikachu444/autonomous-cae-lab/blob/8bd6bd74c2f1932608b1c6c96296216abb6383a5/caelab/workbench.py
[S-POST]: https://github.com/pikachu444/autonomous-cae-lab/blob/8bd6bd74c2f1932608b1c6c96296216abb6383a5/apps/desktop_post/external.py
[S-WORK]: https://github.com/pikachu444/autonomous-cae-lab/blob/8bd6bd74c2f1932608b1c6c96296216abb6383a5/apps/desktop_post/workspace.py
[S-REPAIR]: https://github.com/pikachu444/autonomous-cae-lab/blob/8bd6bd74c2f1932608b1c6c96296216abb6383a5/apps/desktop_post/source_repair.py
[S-CMD]: https://github.com/pikachu444/autonomous-cae-lab/blob/8bd6bd74c2f1932608b1c6c96296216abb6383a5/apps/desktop_post/commands.py
[S-GRAPH]: https://github.com/pikachu444/autonomous-cae-lab/blob/8bd6bd74c2f1932608b1c6c96296216abb6383a5/caelab/connection_graph_native.py
[S-PORT]: https://github.com/pikachu444/autonomous-cae-lab/blob/8bd6bd74c2f1932608b1c6c96296216abb6383a5/caelab/portable_project.py
[S-PLAN]: source-bundle.md
[A-CAD]: https://github.com/pikachu444/autonomous-cae-lab/blob/8bd6bd74c2f1932608b1c6c96296216abb6383a5/caelab/native_cad.py#L201
[A-FORK]: https://github.com/pikachu444/autonomous-cae-lab/blob/8bd6bd74c2f1932608b1c6c96296216abb6383a5/caelab/portable_project.py#L425
[A-WB]: https://github.com/pikachu444/autonomous-cae-lab/blob/8bd6bd74c2f1932608b1c6c96296216abb6383a5/caelab/workbench.py#L70
[A-LINK]: https://github.com/pikachu444/autonomous-cae-lab/blob/8bd6bd74c2f1932608b1c6c96296216abb6383a5/caelab/desktop_links.py#L1
[A-CMD]: https://github.com/pikachu444/autonomous-cae-lab/blob/8bd6bd74c2f1932608b1c6c96296216abb6383a5/caelab/native_commands.py#L1
[A-DESKTOP]: https://github.com/pikachu444/autonomous-cae-lab/blob/8bd6bd74c2f1932608b1c6c96296216abb6383a5/apps/research/desktop.py
[W-PV]: https://docs.paraview.org/en/v6.2.0/UsersGuide/savingResults.html
[W-VTK]: https://docs.vtk.org/en/latest/vtk_file_formats/vtkxml_file_format.html
[W-READER]: https://www.paraview.org/paraview-docs/v6.0.0/python/paraview.simple.html

[A-ANALYSIS]: https://github.com/pikachu444/autonomous-cae-lab/blob/8bd6bd74c2f1932608b1c6c96296216abb6383a5/apps/desktop_post/analysis.py#L405

## 구현 적용 메모 — Codex, 2026-10-16

위 본문은 실제 Pro 교정02의 채택 설계다. 구현 중 확정한 아래 사항은 Codex의 적용 결정이다.

saved import의 첫 저장이 만드는 `native/<K>/target.json`은 기존 NativeTarget의 운영 기록이다.
원 manifest를 바꾸거나 새 범용 registry를 만들지 않는다. 기존 open/action 예약·완료 Save·등록
참조와 결속해 검증하고 head를 마지막으로 발행한다. 취소·미완료 예약은 완료 목록에 넣지 않는다.

선언된 unavailable history의 현재 존재하는 asset도 기존 RelocationRecord의 derived_members에
원 member와 현재 상대 위치·파일 pin의 대응으로 보존한다. 원 record·hash·누락 상태는 유지하며
옛 경로를 따라가는 복구는 하지 않는다. 이 대응은 첫 저장 뒤에도 남아 재복사·새 프로세스에서
검증되어야 한다. available history의 수치 검증이나 누락 자료의 성공 판정을 대신하지 않는다.
