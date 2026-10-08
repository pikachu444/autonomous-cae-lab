# 전처리와 후처리 검증 기록

2026-10-08 · **기획 미완료. 이전 HTML GUI 구조안은 철회했으며, 이후 FreeCAD/ParaView native 연결 시안을 별도로 보존했다.** 요구사항·설계 초안은 [PREPOST_APP_SPEC](PREPOST_APP_SPEC.md), 재사용 근거는 [PREPOST_REUSE](PREPOST_REUSE.md). 사용자 수용 및 제품 전체 완료는 미확인이다.

## Native 시안 보존 체크포인트

사용자가 설계 재검토 자료의 Space 업로드와 현재 작업의 push 및 준비된 변경 병합을 요청했다. 아래는 제한된 시안의 관찰이며 최종 도구 선택이나 5개 앱 전체의 수용이 아니다. 원격 main `fc7c82dfcf4a6155ff18b7ebd5b91388916e6a9e`의 기존 Workbench 구현을 보존하고 새 시안만 통합한다. 아래 원래 관찰은 local `4843c66` 및 당시 미커밋 native 소스에서 수행됐다. 나중의 공개 커밋이나 문서 갱신을 새 native 시험으로 계산하지 않는다.

- FreeCAD 1.1.4 실제 편집/Undo/Redo/Gmsh/저장·재열기: `runs/pre-native-verify-20261008-162023/verification.json`, SHA-256 `e5f652beb0c74beddc902e22c5c1d2af3a1d068922b4fad5cd9471b71a2a7c1f`. 길이 38→40 mm에서 부피 변화 후 원상복원, 31,729 절점/20,297 체적 요소와 저장 후 재열기, 원본 CAD 해시 불변. 이 사례는 일반 CAD·조립 운동 검증이 아니다.
- ParaView 6.2 native reader: `runs/desktop-post-20261008-03/native_reader_verification.json`. A/B 각각 9,155 절점/5,319 요소의 모든 ID·좌표·변위·연결 순서를 원본과 대조했다. 최대 성분 차이는 0이며 새 solver 실행은 없다.
- ParaView 명령/비교/저장·복원: `runs/desktop-post-20261008-03/verification-20261008T075108Z-aa1608/report.json`, SHA-256 `c67d953742140b4008a97cac1790f6447aa17bf23d2a644c196c2f54836defa6`. 모든 차이·변화율과 0 분모 mask, 실제 node331 탐침, 변경된 reader/원본 해시 거부, 보간 결과에서 원본 ID 제거, 저장 후 복원을 확인했다. 이 headless receipt의 `gui_verified=false`는 유지한다.
- 별도 실제 GUI 관찰: 3D 결과·단면·곡선, A/B 공통 범례, 차이 보기, node331 탐침, 새 Slice, 저장·재열기. 캡처는 같은 run의 `gui/`에 보존했다. 마지막 GUI 저장은 `saved/20261008T081551Z-9b18c7/project.json`. 전체 GUI 수용, 조립 운동, CAD 없는 작업, 일반 비교와 대형 성능 검증을 뜻하지 않는다.
- 실패 보존: 초기 Post run01/02, run03의 startup-diagnostic-01..06은 삭제하지 않았다. 분리된 `--log` 인자가 있는 시작 실패는 equals 형식 인자로 수정했다. .NET/Start-Process 수명 차이를 원인으로 확정하지 않는다.
- 공개 전 독립 검토에서 기존 output 거절 뒤 `failure.txt`를 덮어쓰는 결함과 다른 입력을 고정 150N/200N 이름으로 표시하는 결함을 수정했다. 새 디렉터리를 만든 경우만 실패 기록을 쓰고, 이 시안의 고정 표시와 다른 원본 metadata는 view 생성 전에 거부한다. 관련 회귀 및 structural field 검사 187개가 최신 main을 통합한 `fdbc9e9001f3a1ae189736d8aa6d6c98539e36b0`에서 통과했다. 이 수정 후 새 native/GUI 시험은 수행하지 않았다.

원본 실행 자료·설치 런타임은 로컬에만 있으며 Git에 포함하지 않는다. 공개 기록은 [20261008-native-prepost-checkpoint](../benchmarks/records/20261008-native-prepost-checkpoint.json), 설계 검토 자료는 [Space](https://chatgpt.com/space/page_6ac79c9b17c48191a63e2775c75fa1d2)에 둔다. 다음 단계는 전체 변경 설계안 검토이며 기존 Core MCP/수치 엔진과 native 앱 제어를 함께 정리한다.

## 시작 상태와 원본 보존

- local HEAD `4843c66e482ded31c59604d7cc19d1800be388f4`, origin/main `fc7c82dfcf4a6155ff18b7ebd5b91388916e6a9e`, pinned fixture `3e48bf6138f495299f45b1af254bfb4aaff307b8`.
- 기존 dirty: `apps/lab/service.py`, `scripts/verify_fixture_selected_research_source.ps1`, `scripts/verify_mcp.py`; 기존 untracked `docs/CAE_SYSTEM_IMPLEMENTATION_SPEC.md`. 보존 대상이며 이 작업에서 편집하지 않는다.
- 새 실제 시험 경로: `runs/prepost-session-20261008-01`. 이전 실험 `C:/Users/pikac/Documents/Codex/2026-10-08/new-chat/work/cad-reuse-spike`는 read-only reference다.
- 원문 attachment, Space 네 페이지를 실제 읽었다. 상세 페이지는 기본 read 용량을 넘어 full read로 회수했다. HyperMesh property 화면 및 반려 Windows pre-material 화면을 이미지로 확인했다.
- 정확한 local4843 CI37547439489는 core/research-source 실패·나머지8 skip. remote fc7 CI37698069804는9 pass·Code_Aster 실패. 전체 통과나 새 solver 검증으로 사용하지 않는다.

## 실제 화면 관찰

| 관찰 | 조작/기대 | 실제 관찰 | 판정 |
|---|---|---|---|
| 기존 Windows pre 시안 | 기존 unsaved 창 read-only 관찰 | 초기 minimized capture 실패, activate/rebind 후 실제 screenshot 성공. 하중 조건 선택인데 중앙은 무관한 곡선이며 native 3D target 미노출. 기존 수정 내용 건드리지 않음 | 반려 원인 재현. 수정본 합격 아님 |
| HyperMesh reference | source image 열기 | 유형별 property tree, ID/name/include, 선택 PSHELL property1→같은 ID12 Entity Editor/Material | 실제 공식 화면 참고, 직접 제품 조작 아님 |

## Ouroboros 실행

- 스킬: interview/seed/research 원문 읽고 적용. runtime `work/ouroboros-venv`, source0.55.6.
- 노출 tool discovery에 Ouroboros가 없어 실제 local MCP client를 이용한다. 8765 기존 listener 없음. 새8766 bind 시 실패했고 정체 불명 endpoint initialize는 error로 끝남; 채택/조작하지 않음. 이후 owned stdio transport로 전환.
- stdio initialize/list_tools는 성공. 첫 print만 CP949 UnicodeEncodeError; UTF-8 stdout으로 교정. 설정·자격증명 변경 없음. event DB는 새 run 경로, 새 interview ID만 생성한다.
- 실제 interview 생성·재개와 사용자 답 7건 저장까지 완료했다. 현재 session은 `interview_20261008_044855`이며 이후 GUI 구체화 지적을 받아 주 담당의 완료 판단은 보류 중이다. tool listing을 interview 성공으로 세지 않는다.

## 현재 gate

V01–V15는 새 GUI/manifest로 아직 통과를 주장하지 않는다. FreeCAD/ParaView 공식 portable archive의 다운로드·추출은 완료됐지만 새 앱은 실행하지 않았다. FreeCAD archive SHA256은 공식값 `4828741fc91ee37fafcdb97a1abacb18b04ba451ac4372d9ff7a7349b36f4d6d`와 일치한다. ParaView는 공식 다운로드에서 수신했으며 게시 checksum과 대조는 아직 하지 않았다.

## 첫 사용자 질문과 대기 상태

사용자는 총괄을 통해 "질문 없이 계속하지 말고 이 채팅에서 바로 물어보라"고 수정 지시했다. 추가 다운로드·시안 구현·명세 확정을 중단했다. A의 새 post fixture 작업도 중단했다. 이미 작성된 명세/재사용 조사는 미승인 초안이며 제품 선택을 대신하지 않는다.

사용자에게 실제 제시한 질문:

> 전처리에서 CAD를 어디까지 편집하고 싶으신가요? STEP을 해석용으로 손질하는 수준과, 스케치·치수·피처 이력을 갖는 설계까지 직접 하는 수준은 앱 구성이 달라집니다. 조사한 FreeCAD는 두 경로의 재사용 후보입니다.

선택지:

1. 해석 준비 중심: 가져오기·치수 변경·분할·구멍/필렛 제거·영역 지정까지 먼저 완결 (권장)
2. 설계까지 포함: 스케치·구속·피처 이력·부품/조립 설계도 전처리 안에서 편집
3. 기존 CAD에서 설계: 전처리는 가져온 형상·메시·재료·조건 준비에 집중

답변: **사용자가 2번을 선택함.** 정확한 답: "설계까지 포함: 스케치·구속·피처 이력·부품/조립 설계도 전처리 안에서 편집". 따라서 해석 준비에 한정한 권장안은 채택되지 않았다. 스케치·구속·피처 이력·부품·조립 설계를 전처리 내부 범위로 포함한다. 조립 기능의 세부 깊이는 아래 질문2에서 추가로 확정했다.

실제 Ouroboros `interview_20261008_044855`가 생성되고 같은 CAD 범위 질문을 반환했다. 초기 client의 timedelta timeout 인자 오류 후 float로 수정하여 동일 session resume에 성공했다. UTF-8 stdout 및 float timeout은 총괄도 설치 SDK와 대조했다. 2026-10-08 04:59:27 UTC interview 성공, 05:01:48 UTC 실제 첫 답 저장, 05:02:24 UTC owned stdio 정상 종료를 로그로 확인했다. 상태는 첫 답 제출 후 1 answered / 2 total, pending question, ambiguity_score=null, seed_ready=null이다. 정확한 request/response는 새 run의 `interview-*.json`, event DB와 로그에 보존했다. Seed는 생성하지 않았으며 인터뷰 완료를 주장하지 않는다.

### 질문 순서와 출처 구분

1. CAD 편집 깊이: 도구와 사용자에게 제시한 질문의 의미가 일치, 사용자 '설계까지 포함'을 실제 MCP에 기록했다.
2. 조립 설계 깊이: **진행자가 추가한 질문**이며 도구가 반환한 round 2 질문과 다르다. 실제 질문은 "조립 설계에는 어느 수준까지 필요하신가요? 부품을 조립해 해석 조건을 만드는 작업과, 관절을 움직여 기구의 운동을 검토하는 작업은 필요한 명령과 검증이 다릅니다." 사용자 답은 "위 기능에 관절 운동·운동 경로·기구 동작 검토까지 포함". 이 답을 CAD 창 진입 방식의 답으로 연결하지 않는다. 정확한 last_question으로 별도 기록해야 한다.
3. CAD 편집 진입 방식: 도구가 반환한 round 2 질문. 실제 사용자에게 "‘전처리 안에서 설계 편집’은 어떤 사용 경험이어야 하나요? 기존 CAD 기능을 재사용하더라도, 창을 오가는 방식과 문서·미저장 상태를 한곳에서 다루는 방식은 다릅니다."라고 제시했다. 사용자 답: **"같은 전처리 창에서 CAD 설계 모드로 전환하고 문서·미저장 상태를 함께 관리 (권장)"**. 별도 CAD 앱 창 왕복은 전처리 목표 경험에서 제외한다. 후처리 host에 관한 답으로 자동 확장하지 않는다.

질문2는 추가 사용자 결정이며, exact last_question과 함께 MCP에 제출해 2 answered / 3 total 상태로 저장했다. 질문3은 원래 도구 질문에 대한 실제 사용자 답이다. 둘을 혼동하지 않는다. 이후에는 도구가 반환한 질문을 라우팅하고 정확한 질문·답 매칭을 유지한다. 도구 생성과 실제 제시 질문의 문구/범위 차이도 위와 같이 기록한다.

### 질문4와 독립 검토

질문3 답변도 실제 MCP에 저장했다. `interview-answer-03-result.json`은 3 answered / 4 total, pending=true, ambiguity=0.1335, seed_ready=true를 반환했다. 그러나 completion_qualified=false이며 이유는 Success Criteria Clarity 0.69 < 0.70이다. 모호성 점수나 seed-ready 신호를 사용자 수용 또는 기획 완료로 해석하지 않는다.

도구가 생성한 질문4:

> 이번 기획 검증에서는 같은 전처리 창에서 ‘구속 스케치로 부품 생성 → 피처 수정 → 두 부품의 관절 조립·운동 경로 확인 → 저장·종료·재열기 후 이력과 관절 복원’까지 연결된 대표 사례 하나를 실제 조작할 수 있어야 수용하시겠습니까(문서 관리와 기능 연결을 함께 검증할 수 있어 권장), 아니면 설계 편집과 운동 검토를 각각 별도 시연으로 입증해도 충분합니까?

실제 사용자에게 제시한 문구:

> 이번 전처리 시안의 검증은 어느 방식이어야 하나요? Ouroboros는 ‘구속 스케치로 부품 생성 → 피처 수정 → 두 부품의 관절 조립·운동 경로 확인 → 저장·종료·재열기 후 이력과 관절 복원’을 한 흐름으로 직접 조작하는 기준을 제안했습니다. 이 사례가 전체 제품 범위를 제한하지는 않습니다.

선택지: (1) 한 문서의 연결된 흐름으로 실제 조작·저장·복원을 검증 (권장), (2) 설계 편집과 조립·운동 검토를 별도의 실제 시연으로 검증해도 충분. 이후 질문 UI가 활성화되지 않아 사용자가 일반 채팅 답변을 요청했다. '문서'는 보고서가 아니라 부품·조립·설정을 저장하는 CAD 작업 파일/프로젝트라고 설명하고, 전체 과정의 연결 시연과 개별 시연 중 선택하는 질문을 일반 채팅으로 제시했다. **사용자 답: "응 권장안으로 진행".** 전체 연결 검증을 이번 시안의 필수 기준으로 채택한다. 논리적으로 하나의 작업/프로젝트를 뜻하며 단일 물리 파일 포맷을 강제하지 않는다. 정확한 설명과 답변은 `interview-answer-04.json`으로 MCP에 기록했다.

두 기존 담당자만 재사용해 advisory 6개 lane과 lateral 3개 persona의 지정 payload를 읽기 전용으로 처리했다. `ouroboros_submit_fanout_results`와 `ouroboros_fetch_artifact`까지 실제 호출했으며 모두 complete, contract_violations={}, undispatched_keys=[]였다. 기록은 같은 run의 `advisory-*`, `lateral-*` JSON에 보존했다. 반환 계약은 `fanout:7cc72b3e5d6eeb5719200f0066bf15659807c06a2bfb9aad4d16c1c1245c12ed`와 `fanout:b5899f7e46870b63b744ce4eba09f3b2686f95f1a8bafe0f277b66a1b3f26e9e`이다.

검토에서 기능 존재와 제품 통합 검증을 구분하고, 형상 변경 뒤 관절/조건 참조 무효화·Undo·저장 복원을 확인해야 한다고 정리했다. 운동 정의 복원과 계산 프레임/궤적 보존은 별개다. 실제 운동 시연도 힘·접촉·응력 해석의 근거로 확대하지 않는다. 후처리 외부 자료·위치 ID·출처·저장 복원 및 전처리의 CAD 없는 자료 작업은 독립 요구로 유지한다. 이 검토 결과는 사용자 답변을 대체하지 않는다.

질문4 이전 closer/contrarian/gap_hunter 검토는 closer=blocked, contrarian=HIGH, gap_hunter=HIGH였다. 핵심 사용자 판단이었던 Q4는 위 답변으로 해결했다. 비CAD 재료점/PDE 작업의 편집·Undo·저장·재개, 후처리의 상이한 시간축·단위·mesh 비교와 보간, fullCAD 명령·검증 연결은 기존 요구를 담당자가 명세해야 하는 작업이다. 포함 여부를 사용자에게 다시 묻지 않는다. GUI 실험 미완료 자체를 Seed 작성의 선행 사용자 결정으로 삼지는 않는다.

### 질문4 저장 후 현재 상태

실제 `interview-answer-04-result.json`: 4 answered / 5 total, pending=true, ambiguity=0.036, seed_ready=true, completion_qualified=true, floor failures 없음, candidate streak=1/2. 아직 전체 사용자 수용·Seed 완료로 해석하지 않는다.

도구 질문5: "확정한 전처리·후처리 전체 범위, 현재 명세·검증기록·핵심 시안·후속 구현 작업, 그리고 내부 검토와 구분되는 사용자 수용 외에, 이번 기획 검증에서 빠지면 수용할 수 없는 요구나 예외가 더 있나요?" 일반 채팅으로 질문하고 사용자의 자유 답변을 받는다. 사용자 요구에 따라 질문 UI는 사용하지 않는다. 기술 명세 보완·closure 재검토·목표 재진술 확인 뒤 실제 Seed 생성으로 진행한다. 추가 제품 구현과 시안 실행은 인터뷰보다 앞세우지 않는다.

### 질문5 사용자 지적: 메시와 결과 보기

사용자 원문: **"메시 기능이나 결과 보기 관련된것도 다뤄야하나 아닌가?"** 추가 요구가 없다는 답이나 종료 동의가 아니다. 주 담당은 메시 생성·품질·영역 지정 및 결과 위치·시간·성분·단면·탐침·비교가 원래 요구임을 확인하고, CAD에 편중된 인터뷰의 종료를 보류했다. 사용자 원문을 `interview-answer-05.json`으로 제출하고 이 범위의 아직 정하지 않은 제품 동작을 실제 도구 질문으로 이어간다.

앞선 guard의 '추가 사용자 판단은 Q4 하나뿐'은 이 지적 이전 검토이며 최신 완료 근거로 사용하지 않는다. 메뉴/기능 포함 여부와 필요한 조작 깊이를 구별한다. 이미 확정된 범위를 줄이거나 담당자의 기술 결정을 사용자에게 전가하지 않되, 메시·결과 보기의 사용자 의도를 CAD 답변만으로 추정하지 않는다.

### 질문6: 메시 개선 방식

질문5 사용자 원문은 실제 MCP에 저장됐으며 결과는 5 answered / 6 total, pending=true, ambiguity=0.15, completion_qualified=false, criteria clarity=0.69로 종료가 보류됐다. 도구 질문6은 국부 크기·분할 설정을 조정해 다시 생성하는 흐름과 직접 절점 이동·요소 삭제·재연결까지 필요한지 비교했다. 일반 채팅으로 같은 선택을 제시했다.

**사용자 답: "일단 1번".** 현재 단계는 설정을 통한 재메시 개선을 채택한다. 직접 mesh 편집의 영구 제외로 확대하지 않는다. 실제 메시 생성·품질검사·불량요소 선택·국부영역 강조·조건 재검증·설정 저장·재열기 및 이전 메시 보존을 P06/P07/V03에 반영했다. 정확한 실제 질문과 원문 답을 `interview-answer-06.json`으로 기록해 동일 MCP session에 제출했다. 결과 보기의 미정 제품 동작도 이어서 확인한다.

### 질문7: 결과 비교 깊이

질문6 결과는 6 answered / 7 total, ambiguity=0.102, completion_qualified=true, streak=1/2였다. 도구 질문7은 같은 부품의 조건 변경 결과를 나란히/겹쳐 보는 수준과, 차이값·변화율 필드/곡선을 계산·표시·저장하는 수준을 비교했다. 일반 채팅으로 그대로 두 선택을 제시했다. **사용자 답: "2번".** 후자를 Q09/Q09a/Q09b에 반영하고 정확한 질문·원문 답을 `interview-answer-07.json`으로 동일 session에 제출했다. 실제 계산 성공을 주장하지 않으며, 비교 규약·단위/위치/시간 대응·0 분모 및 mask 처리의 기술 제안과 실제 사용자 선택을 구분한다.

### GUI 구체화와 진행 방식에 대한 사용자 지적

실제 answer07 도구 결과는 phase=complete, 7/7 answered, pending=false, ambiguity=0.0975, completion_qualified=true, streak=2/2였다. 그러나 사용자가 **"GUI를 어떻게 구성할지도 고민이 필요하지 않나?"**, 이어 **"왜이렇게 수동적으로 일하지. 이거 중요한건데 고민 좀 많이 해주면 좋겠어. 나 답답해."**라고 지적했다. 질문 수치의 종료를 전체 기획 완료로 확장하지 않는다. 사용자 GUI 지적은 아직 실제 MCP의 새 질문/답변으로 제출하지 않았으며 임의로 답변·승인을 만들지 않는다. Seed는 생성하지 않았다.

주 담당은 기능 질문 중심 진행을 바로잡아 PREPOST_APP_SPEC 3절에 작업 대상/명령 모드/선택·고정 task 대상/변경 영향/메시 개선 왕복/결과 비교/저장 명령을 하나의 GUI 흐름으로 정리했다. A는 native 상태·transaction·save·selection 제약, B는 명령 발견·대상 혼동·오류 복구·데이터 작업·재개를 독립 검토했다. FreeCAD native preview가 working document를 바꿀 수 있다는 점을 반영하여 'Apply 전 모든 native 문서 불변'을 'committed revision과 실행 입력 불변, Cancel transaction rollback'으로 정정했다.

화면 구조 시안: `C:/Users/pikac/.codex/visualizations/2026/10/08/01a119cd-3a3d-7303-a0f9-6e8a4eadf63d/prepost-workspaces.html`. 기본 패키지/모델 작업의 명령 분리, 객체 트리·중앙·속성 관계, 후처리 A/B·차이 배치를 탐색하는 **개념 구조 시안**이다. 실제 CAD/계산 미연결을 시안 상단에 표시했다. 로컬 브라우저에서 실제 캡처 이미지를 보고 전처리→자료 작업 전환 및 후처리→비교→차이 버튼을 클릭해 변경된 상태를 관찰했다. CAD 없는 자료 모드에서 CAD 명령이 숨겨지고 중앙·트리·속성이 함께 바뀌는 것을 확인했다. 첫 검토에서 작업 대상별 명령 분리와 차이 중앙영역 전환을 보완한 뒤 재확인했다. 이 결과는 Windows native 앱 V01–V15 통과가 아니다.

추가 advisory의 answer04/05/06별 6개 lane도 두 담당자가 원문 payload로 처리한 뒤 실제 submit/fetch까지 완료했다. 모두 status=complete, contract_violations={}, undispatched_keys=[]였다. 응답은 같은 run의 `advisory-04/05/06-*-result.json`에 보존했다. 비교 계산의 범위 선택과 수학적 규약의 기술 제안을 분리하고, 메시 선택의 '일단'을 후속 검토 경계로 유지했다.

### 화면안 철회와 기획 상태 정정

사용자 지적: "한참 기다려서 만든게 이건가? 하이퍼메시나 다른 툴들하고 비교해보면 너무 이상하지 않나? 아무튼 기획 다 끝난거지? 니가 작성한거대로 만들면 저거 대로 만드는거야?"

주 담당 판단: 기획은 끝나지 않았다. 기존 문서가 패널 위치·폭·작업 모드를 지시하므로 그대로 구현하면 제시한 시안과 비슷한 구조가 될 위험이 실제로 있다. 이를 단순한 개념도라는 설명만으로 회피하지 않는다. 제목·상태·3절을 수정해 해당 배치를 철회하고 구현 인계 불가를 명시했다. HTML은 이전 시안 기록으로 보존한다. 기능 요구와 데이터/편집/보존 원칙은 삭제하지 않는다.

HyperMesh Model Browser/Entity Editor 및 ANSYS Mechanical의 공식 인터페이스 자료를 읽고 개체 조작·표시·속성 편집·선택·맥락 명령 측면의 결손을 초안에 기록했다. 상용 앱의 실제 실행 또는 새로운 CAD/mesh/result GUI 검증을 수행한 것은 아니다. 새 Seed 생성, 기획 수용, 전체 V01–V15 통과도 여전히 없다. 다음 설계는 실제 엔지니어링 작업과 native 도구 재사용 근거로 보완해야 하며, 방금 시안에 외형만 추가해 완료 처리하지 않는다.

impeccable의 bounded 검토를 적용했고 detect는 task 구분선의 좌측 padding warning 2건을 반환했다. 실제 캡처에서 해당 영역은 위쪽 구분선과 충분한 상단 간격을 가지므로 화면 결함으로 승격하지 않았다. 전체 app·native host 통합 성공이나 접근성 전체 합격은 주장하지 않는다.
