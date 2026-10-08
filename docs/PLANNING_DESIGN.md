# Autonomous CAE Lab 상세 제품 설계

2026-10-08. 설계 검토용 현재본. 기준 원문은 기존 Space 상세 기획 페이지이며 이 파일은 구현 인계용 사본이다. 첫 전체 구성안을 아래에 먼저 확정하고 화면 검증에 따라 같은 파일을 수정한다. 제품 전체 구현 완료를 뜻하지 않는다. 코드 기준 remote main `fc7c82dfcf4a6155ff18b7ebd5b91388916e6a9e`.

## 1 전체 구성과 실행 경계

주 실행 경로는 **Windows에서 로컬 서비스를 자동 기동하는 웹 작업 공간**이다. 하나의 UI 구현을 공유하되 각 앱은 자기 시작 항목, 창, 문서, 메뉴, 저장과 복구를 가진다. Workbench 창 없이 각각 시작·작업·종료할 수 있어야 한다. URL 여섯 개를 만드는 것만으로 독립성을 인정하지 않는다. 별도 네이티브 GUI를 병행 개발하지 않는다. 데스크톱 포장은 파일 연결과 실행 수명 검증 이후 선택한다. 계산 프로세스는 GUI 창 수명과 분리한다.

| 프로그램 | 주 대상과 역할 | 입력 → 출력 | 저장 단위와 소유권 | 실행 경계 |
|---|---|---|---|---|
| 전처리 | 모델/메시/영역 또는 실험 곡선/구간 편집. CAD 없이 재료점·PDE 연구 시작 | CSV/ASCII, 지원 메시, 재료·조건 → 검증한 Case revision 및 원본 참조 | `.caeprep` 문서: 편집 객체, 조건, 매핑, 단위, 뷰. 원본 불변 | 열기·편집·검증·내보내기. 계산 제출은 실행기에 넘김 |
| 솔버 실행기 | 케이스와 실행 이력, 큐, 로그/수렴 | 고정 Case revision·backend 설정 → Run, Result 참조 | `.caerun` 실행 묶음: 입력 스냅샷, 로그, 산출물 manifest | backend별 검증·실행·중단·재실행. AI 필요 없음 |
| 후처리 | 필드 또는 곡선, 위치/시간/성분, 동기 비교 | Result 또는 외부 ASCII → Analysis, 추출 파일 | `.caepost` 분석 문서: 원 결과 참조, 프레임, probe, 축, 비교 규칙 | 원 solver 없이 결과 열기. 파생량만 별도 저장 |
| 최적화 | 평가 절차, 설계 변수/응답, 설계 공간/후보 | Case·평가기·실험 target → Study, Candidate, 각 Run | `.caestudy`: 절차, 범위·단위, 목적·제약, 고정 입력, 후보/예산/이력 | DOE/동정/최적화/UQ/민감도/대리모델. 수치 평가기는 기존 라이브러리 |
| 전문가 자문 | 발언·응답 관계를 가진 대화, 근거/논점 | 자유 질문, 관측·결과·허용 범위 → 메시지/논점/실행 제안 | `.caechat`: 세션, 발언, 근거 참조, 권한 범위, 제안과 결과 관계 | 프로젝트 없이 자문. 모델 미연결 시 초안 작성·저장은 가능, 생성 불가 |
| Workbench | 프로젝트 객체와 시스템 연결, 버전/영향 | 위 저장 객체·호환 포트 → 연결 그래프/열기 요청 | `.caeproject`: ID/revision 참조와 연결, 레이아웃. 결과를 복제 소유하지 않음 | 조정자. 하위 앱 기능을 축약 폼으로 재구현하지 않음 |

공통 로컬 서비스는 파일/객체 저장, 버전 비교, 기존 job/result API를 제공한다. 비AI 네 프로그램은 AI 계정·MCP·OpenScience·CAD 설치 없이 시작한다. 호환이 없는 backend만 해당 실행을 비활성화한다. API/CLI와 GUI는 같은 계산 함수를 사용한다.

## 2 전체 화면과 이동 구조

각 앱은 시작/최근 문서 → 작업 문서 → 저장/종료/복구의 구조를 가진다. 파일 가져오기와 실행환경은 보조 대화상자다. 중앙 문서는 메뉴 이동에도 보존된다. 문서 탭은 앱 내부의 열린 대상이며 앱 독립성을 대체하지 않는다.

| 앱 | 주 화면과 보조 화면 | 객체 트리 | 중앙과 선택 연동 | 메뉴 및 이동 |
|---|---|---|---|---|
| 전처리 | 모델, 곡선, 재료점 이력, PDE 영역/약형식; 가져오기 매핑, 재료/조건 편집, 품질 진단, 내보내기 | 데이터셋/열/곡선/구간, geometry/mesh/set, material, condition, validation | 면·절점·구간 선택 ↔ 같은 ID의 트리 강조 ↔ 해당 속성. 지원 없는 모델은 빈 3D 장식 대신 형식 안내 | 파일/편집/선택/재료/조건/검증/보기. 진단 클릭으로 문제 대상 복귀 |
| 실행기 | 케이스/실행 큐, 선택 실행 로그와 수렴; 환경/자원, 입력 점검, 실패 상세 | case/revision, queued/running/history run, output | run 선택 시 입력 revision·로그·곡선·결과가 함께 전환 | 파일/케이스/실행/중단/결과/보기. 완료 Result를 후처리로 열기 |
| 후처리 | 필드, 이력곡선, 나란히 비교; ASCII 매핑, 성분/단위, probe/추출 | result/run, field/component/frame, channel/probe, derived/comparison | 위치·시간·성분 선택이 범례·축·속성과 같은 데이터 ID를 가리킴 | 파일/선택/표시/비교/분석/내보내기. 원 실행은 읽기전용 열기 |
| 최적화 | 평가 절차, 설계 공간/Pareto, 후보 비교; 변수·목적·제약, DOE/예산, 실패 재평가, UQ/대리모델 | study, evaluator/step/port, variable/response, candidate/run | 노드 선택은 입출력과 검증, 후보 점 선택은 변수·목적·제약·곡선 동시 갱신 | 파일/절차/연구/실행/탐색/비교. 후보를 전처리·후처리·실행기에서 정확한 버전으로 열기 |
| 전문가 | 채팅, 논점 지도, 근거 열람; 참여자/모델, 자료/허용 범위, 실행 제안 검토 | session, evidence, issue, proposal/job | 메시지 reply-to → 원 발언, 근거 → 원문, 논점 → 관련 메시지. 진행자와 전문가 발언 구분 | 세션/자료/참여자/일시중지/이어가기/결론. 하단 입력은 항상 접근 가능 |
| Workbench | 프로젝트 연결도, 변경 영향/이력; 객체 등록, 포트 연결, 깨진 경로 복구 | project/system/object/revision, link, job/result | 노드·선 연결 선택 → 입력/출력/버전/영향. 더블클릭 → 해당 앱 문서 | 파일/추가/연결/열기/갱신/이력. 저장 후 앱 왕복 시 변경 이벤트 반영 |

## 3 시작부터 종료와 재개까지

1. **재료/실험:** 전처리를 직접 시작해 CSV를 열고 열·단위를 매핑한다. 곡선의 구간을 선택해 유효 범위/가중치를 편집하고 `.caeprep` 저장한다. 실행기에서 이 revision을 검증·계산하고 후처리에서 실험과 응답을 겹친다. 최적화는 이 평가기와 target을 받아 다중 계수와 holdout을 설정한다. 후보를 선택해 잔차·제약·결과를 비교하고 각 문서를 저장한다. 모든 창 종료 후 최근 문서/파일 열기로 같은 revision과 선택을 복원한다.
2. **PDE/구조/충격:** 전처리에서 영역/mesh/set과 식·재료·조건을 지정한다. 진단의 오류 대상을 고친 후 Case를 고정한다. 실행기의 지원 backend로 제출, 중단 또는 실패 원인을 확인한다. 완료 결과를 후처리로 열어 프레임/성분/위치 이력을 선택하고 저장한다. 중단 후 재시작은 backend checkpoint 지원 여부를 따르며 미지원이면 새 run으로 재실행한다.
3. **외부 결과만 있음:** 후처리를 직접 시작해 ASCII를 가져온다. 구분자/열/단위/시간을 미리 보고 등록한다. solver 없이 비교·추출·저장·재개한다. 후보 계수표가 있으면 최적화 연구에 연결하되 없는 후보의 실제값을 만들어내지 않는다.
4. **자문/VOC:** 전문가 앱에서 질문과 관측을 입력하고 자료를 지정한다. 진행자·전문가 메시지와 reply 관계를 읽다가 일시정지해 추가 관측을 보낸다. 후속 발언이 어떤 관측을 반영했는지 확인하고 근거/미해결 논점을 연다. 실행 제안을 검토해 기존 앱에서 편집·실행한 결과를 원 세션에 참조로 돌려준다. 저장 후 세션을 열면 대화/근거/제안 상태를 복원한다.
5. **Workbench 왕복:** 단독 앱의 저장물을 등록하고 포트를 연결한다. 노드에서 정확한 revision을 연다. 전처리 저장으로 새 revision이 생기면 그 입력에 의존하는 실행/연구만 갱신 필요로 표시한다. 과거 결과는 고정 입력과 함께 그대로 열린다. 사용자가 갱신 실행을 눌렀을 때 새 run이 생성된다. 프로젝트를 다시 열면 연결/현재 revision/이전 결과가 유지된다.

## 4 코드 재사용과 첫 결정

초기 대조: `apps/lab/static/workbench.*`, `index.html` 및 `app.js`는 기존 통합 웹 화면이다. `apps/lab/server.py`, `workbench_routes.py`는 현재 HTTP 연결을 제공한다. `caelab/engine.py`, `evaluation.py`, `registry.py`, `jobs.py`, `storage.py`, `response_*`는 계산·기록·조회 재사용 대상이다. 파일 응답은 `adapters/file_table`, `adapters/external_files`, 수치 연구는 `optimizers/scipy_lhs.py`, `scipy_de.py`, `probabilistic_analysis.py`, 전문가 검색·자문은 `assist/experts.py`, `knowledge.py`, `literature.py`에 대응한다. 파일 존재와 실제 사용 가능 판정은 구분하며 작은 실험 결과를 `PLANNING_CODE_REUSE.md`에 결합한다.

| 결정 | 현재 권장안 | 확인 방법/영향 |
|---|---|---|
| 주 UI | 로컬 웹 작업 공간 하나, 앱별 직접 launcher/문서 수명 | Windows 실 URL 조작·저장·모든 창 종료/재개. 원격 Cloud 화면은 증거 제외 |
| 수치/자료 | 기존 SciPy/FELUPE/reader/job/result 유지 | 계수 변화가 실제 결과를 바꾸는 작은 연결 실험 |
| 뷰어 | 곡선은 재사용 chart, 메시/필드는 VTK/trame 후보 검증 | 실제 dataset ID 선택과 저장. 불가한 기능은 지원으로 표시하지 않음 |
| 연결도 | React Flow 등 포트/선택 컴포넌트 재사용 후보 | 그래프 저장·복원·오류 표현. 실행 엔진은 기존 코드 |
| 전문가 | 기존 Haystack 경로에 대화·reply/issue UI 연결 | 시안의 고정 응답은 시연으로 표시. 실제 LLM은 승인 endpoint가 있는 경우만 |
| native 도구 | ParaView/FreeCAD/PrePoMax/SALOME은 기능별 보완 후보 | 라이선스·배포·파일 왕복 조사 후 채택 범위 결정, 전부 기본 설치 안 함 |

독립성과 Workbench 구조는 사용자 확정사항이다. 남은 라이브러리/레이아웃 선택은 실제 선택·저장 시험으로 결정한다. 실제 회사 solver·LLM 계정은 기획 완료와 제품 실연결 완료를 나누어 기록하며, 없는 자원을 있다고 전제하지 않는다.

## 5 참고 행동을 우리 명령으로 연결

| 직접 확인한 자료와 성격 | 관찰한 행동 | 우리 대상·명령·결과 |
|---|---|---|
| [Ansys Workbench 공식 도움말](https://ansyshelp.ansys.com/public/Views/Secured/corp/v252/en/wb2_help/wb2h_creating_new_connecting.html)의 `Link_two_systems.gif`, 실제 제품 UI 애니메이션 | toolbox의 시스템을 기존 셀에 연결. 연결 위치에 따라 shared Engineering Data/Geometry/Model과 Solution→Setup 전달이 달라짐 | Workbench의 typed input/output port를 선택할 때 호환 입력·공유 또는 결과 전달을 미리 표시. 연결 후 정확한 객체/revision 열기. Ansys 고정 해석 순서를 전체 분야에 강제하지 않음 |
| [HyperMesh Model Browser](https://help.altair.com/hwdesktop/hwx/topics/user_interface/browser_model_overview_c.htm), 인계 `hypermesh-properties.png` 실제 UI | 속성 객체가 트리에서 선택되고 entity editor가 같은 ID/재료/두께를 보여줌. 공식 문서는 생성 후 그룹에 넣고 새 객체 강조를 설명 | 전처리의 mesh/set/condition tree와 중앙 객체 ID를 공유. 조건 적용 후 새 노드와 대상 표시 갱신; 오류 대상 바로가기 |
| [Synera platform](https://www.synera.ai/platform), 인계 영상 프레임과 공식 설명 | 노드로 처리 흐름을 연결하며 처리 대상은 별도 viewer에서 확인. 프레임은 전체 조작 녹화가 아님 | 최적화 평가 절차의 노드/포트 선택 → 입출력 속성·관련 모델 preview. 처리 상태와 마지막 성공 산출물 분리 |
| [modeFRONTIER 공식 소개](https://www.esteco.com/news/volta-modefrontier-ndai-2026r1/), 인계 workflow/Design Space 캡처 | 절차 편집과 설계 공간·후보표/차트를 서로 다른 작업 문서로 다룸 | 최적화 `평가 절차`와 `설계 공간` 문서 유지, 후보 선택 시 변수/목적/제약/곡선 동시 전환, 기준 후보 고정 비교 |
| [Co-STORM 논문](https://arxiv.org/abs/2408.15232), PDF p23 Fig12/HTML Fig15의 실제 평가용 UI 캡처 | 발언을 클릭해 mind map 강조; continue observe와 사용자의 직접 발언 선택; conversation/article 전환; 발언별 근거 | 전문가 앱 중앙 타임라인과 지속 입력창, 메시지↔논점·근거 연결, 일시정지/끼어들기/이어가기, 결론 별도 문서. 초기 첨부 개념도와 실제 UI 근거를 구분 |

Co-STORM 현 서비스는 약관 동의를 요구하므로 계정·동의·실제 생성을 수행하지 않았다. 위 실제 UI는 저자 논문의 공개 스크린샷이며 서비스를 직접 사용했다는 뜻이 아니다. [공식 소스](https://github.com/stanford-oval/storm)의 `CoStormRunner.step(user_utterance=...)`는 사용자 개입 경계를 확인하는 근거다. 제품 전문가 엔진을 통째로 교체하지 않고 기존 Haystack 경로와 메시지 계약에 이 행동을 적용한다.

## 6 상세 명세와 구현 인계

- `PLANNING_SCREENS.md`: 화면별 목적·트리·중앙 대상·명령·상태·배치.
- `PLANNING_CONTRACTS.md`: ID/revision/단위·출처·호환, 고정 실행 입력, 충돌, 취소, stale와 대화/제안 계약.
- `PLANNING_CODE_REUSE.md`: 실제 코드 판정, 제한 연결 시험, 라이선스·배포를 포함한 재사용 결정.
- `PLANNING_HANDOFF.md`: 기능→화면/명령→API→코드 경로→검증 행동, 선행조건과 완료 기준. UC01–17 범위를 보존한다.
- `WORKBENCH_PROGRESS.md`: 실제 로컬 화면 관찰·수정·재검증과 미완료. 같은 절을 갱신한다.
