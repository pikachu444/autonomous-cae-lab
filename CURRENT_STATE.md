# 현재 작업과 제품 상태

갱신: 2026-10-16. 현재 배정·진행·다음 행동은 이 파일 한 곳에서 관리한다.
제품 목적은 [PRODUCT_PLAN](docs/PRODUCT_PLAN.md), 상세 사용자 작업은
[PRODUCT_UI_MCP_PLAN](docs/PRODUCT_UI_MCP_PLAN.md), 세부 개발·지원·종료조건은
[DEVELOPMENT_ITEMS](docs/DEVELOPMENT_ITEMS.md), 운영은 [CODEX_WORKFLOW](docs/CODEX_WORKFLOW.md)를 따른다.

## 현재 목표와 작업 방식

Windows 로컬의 독립 공학 도구와 전체 연결을 완성한다. FreeCAD FEM·Gmsh·설치된
솔버·ParaView의 native 기능을 재사용하며 전후처리기를 새로 만드는 과제가 아니다.
Data·Material·PDE·Numerical·Runner·Expert·Study는 필요한 외부 도구만 요구한다.
Workbench는 선택 연결 보기다. 제품 주 화면을 웹으로 바꾸지 않고, WSL을 모든 앱의
필수조건으로 삼지 않는다. 추가 지출·유료 API·추가 구독은 0원이다.

2026-10-16 사용자가 "니 맘대로 해봐. 리팩토링인지 뭔지"라고 지시해 리팩토링을 재개했다.
기존 개발 중지 이후의 질문들을 구현 허가로 취급하지 않았으며, 이 최신 지시부터 코드 수정·
영향 검사·통합·커밋을 진행한다. 현재 Goal 도구에는 등록된 Goal이 없고 새 Goal은 만들지 않는다.
우선 범위는 기존 native 전처리 재사용, 제품의 예제 의존 제거와 순수 결과 writer의 앱 역의존
제거다. 기존 조사 결과를 재사용하며 새 전처리기·범용 프레임워크·수치 엔진은 만들지 않는다.
실제 배정은 아래 재개 작업에만 해당한다. 하단의 기존 기능 배정은 중단 전 기록이며 자동 재개하지 않는다.
사용자 미커밋 변경과 미통합 후보를 보존하고 이번 변경과 분리한다.

### 재개 작업

| 범위 | 이번 결과와 쓰기 경계 |
|---|---|
| native Pre | 중복 탄성 물성·기존 고정/힘 값 폼을 FreeCAD Tasks 진입으로 교체해 커밋. 대상 확인·형상 변경 후 방향 복구·지정 변위·Lab 전용 편집 보존. 실제 FreeCAD 수락/취소·입력 생성·저장 재열기 인수는 미완료 |
| Expert 자료 팩 | 제품 loader와 원문·라이선스를 패키지로 이관해 커밋. GUI의 예제 의존 세 곳 제거, 예제 CLI 호환 유지. 예제가 없는 추출 wheel의 자료와 실제 Qt 목록 읽기 확인 |
| 순수 결과 writer | `caelab/adapters/vtu.py`로 이관해 커밋. 여섯 library 호출부 전환, 기존 앱 import 호환과 이관 전후 XML 바이트 일치 확인 |
| 솔버별 기존 전처리 | 실행기 조사를 마침. 현재 검색/선택기는 FreeCAD·ParaView만 등록하며 SALOME-MECA/AsterStudy·OpenCourant 외부 전처리 연결은 미구현. 이번에 새 연결을 구현했다고 표시하지 않음 |

MoAI의 run 절차로 범위·독립 계획 검토·단독 파일 소유·관련 최소 검사를 적용한다.
Astra의 재개 계획·통합 검토를 거쳐 세 수정 범위를 커밋했다. native 편집의 실제 실행 입력
반영과 취소 불변은 다음 직접 인수에서 확인한다. 자료 팩은 원문·라이선스·manifest 바이트를
유지했고, VTU는 이관 전후 출력 바이트와 기존 import 호환을 확인했다.
세부 변경 계약은 [구조 정리안](docs/CODE_STRUCTURE.md)의 재개 작업을 따른다.

### 이번 확인과 다음 행동

Sol 세 담당이 파일을 나눠 작성하고 native 담당과 CAE 자문이 직접 협의했다. Astra가 계획과
실제 반영본을 독립 검토했으며, 방향 복구 경로 누락과 숨겨진 이전 방향의 재주입을 고친 뒤
검토한 변경의 남은 코드 차단 지적은 0건이다. 작은 변경의 새 Pro 요청은 보내지 않았다.
MoAI run 절차와 실제 decision/integration CLI를 사용했고 모델·권한 설정은 바꾸지 않았다.

native 관련 네 검사 파일 93개, 자료 팩/Qt 집중 검사 9개, writer 관련 검사 14개가 통과했다.
Qt 보조 패널의 좁은/넓은 배치와 자료 팩 창을 이미지로 확인했으나 OS 직접 조작 인수는 아니다.
추출 wheel 확인은 배포 자료 포함 검사이며 미통합 사용자 WIP를 포함한 wheel을 출시하지 않는다.
별도 dynamic cold-open 한 검사는 `frozen_input/contact.inp`의 exact-attempt pin 오류로 실패했고,
원래 HEAD writer를 넣어도 동일했다. 이번 추출의 회귀로 숨기거나 고치지 않았다.

다음 최소 인수는 설치 FreeCAD에서 재료·고정·힘 Task 편집과 수락/취소, 대상 변경/복구,
기존 입력 생성의 값 반영과 저장·새 프로세스 재열기다. 현재 Windows 캡처가 지문 잠금 화면이라
입력을 중단했고 native 테스트 앱을 새로 열지 않았다. 잠금 해제 후 이 경로부터 이어간다.
기존 취득·온도 전달·고차면 WIP는 그대로 보존하며 이 인도나 커밋에 섞지 않았다.
코드 두 커밋은 원격 main 반영을 확인했다. Space의 현행 요약도 같은 수정 범위와 native
직접 인수 미완료로 갱신했다. 기존 기능 상태표의 미커밋 변경은 작업 트리에 보존했다.

### 재개 전 조사 기록

아래는 개발 중지 중에 수행한 감사 기록이다. 당시의 '미수정·중지' 표시는 위 재개 작업의
현재 진행 상태와 구분한다.

읽기 전용 분석 결과는 [코드 상태 보고서](_workspace/code-state-audit-20261016/STATUS_KO.md)와
[코드 연결도](_workspace/code-state-audit-20261016/CODE_MAP.svg)에 있다. 온도 전달의
실행 경로 결손과 취득의 저장·시간 구간·선택 문제 등을 확인했으며 제품 교정은 하지 않았다.
사용자의 전체 코드 조사 지시에 따라 [전체 분석 보고서](_workspace/code-state-audit-20261016/full/REPORT_KO.md)와
[파일·함수 탐색기](_workspace/code-state-audit-20261016/full/CODE_EXPLORER.html)로 범위를 넓혔다.
전체 저장소 인벤토리와 1,678개 Python/매크로 구문 분석, 221개 파일의 관련 본문 검토를
구분했다. 신규 기능·복구 결함 15건, 사용성 정책 미적용 2건, 추가 확인 후보 2건이다.
최신 원격 CI는 Windows 한 검사 실패와 Linux 전체 검사 중 crash로 실패했으며
후속 native 계열 검사는 건너뛰었다. 감사 당시 수정·재실행·게시는 하지 않았다.
소스 배치·책임·의존 방향과 기존 파일의 단계별 이동은 [코드 구조 초안](docs/CODE_STRUCTURE.md)에
정리했다. 당시 적용 전 검토안이며 새 폴더 생성·제품 파일 이동·구현 재개는 하지 않았다.
Astra/xhigh의 구조 검토, Sol/high의 소스 교차 검토와 GUI·권한 경계 검토를 마쳤다.
[독립 코드 리뷰와 수정 범위 제안](_workspace/code-state-audit-20261016/architecture/REVIEW_KO.md)에
기존 설계의 재사용 근거, 확인된 결합 다섯 가지와 한정 수정 단위를 정리했다. 전면 재작성이나
폴더 일괄 이동을 권고하지 않는다. ‘패턴이 거의 없다’는 앞선 설명을 교정했다.
같은 보고서에 예제의 사용자 학습·개발 검사·제품의 잘못된 의존·미통합 후보를 구분했다.
대표 실패 주입/제작 응답 코드와 실제 제품 호출을 읽었으며 예제 삭제·이동·실행은 하지 않았다.
사용자가 지적한 전처리의 중복 자체 설정 UI·입력 변환 축소를 같은 수정안의 우선 항목으로
반영했다. 기존 FreeCAD Tasks·native writer 재사용을 기준으로 대체 가능한 코드를 줄이고,
필요한 연구 연계·미제공 요구 기능을 구분했다. 이 시점에는 문서만 반영했다.
개발 중에는 영향을 받은 최소 실행·단위 확인을 수행하며 변경하지 않은 솔버 캠페인을
반복하지 않는다. 테스트로 연 프로그램은 해당 Windows Job/PID만 정리한다.
사용자 세션을 이름으로 종료하지 않는다.
대화 캡처·전달 기록·해시 목록을 사용자에게 진행 성과로 제출하지 않는다.

**역할:** Pro는 전체 설계·상세 명세·중요 판단, Sol 담당은 의미 있는 기능의 코드·GUI·
검사·사용법, Codex는 공통 경계·실행 확인·통합·게시, Astra는 핵심 통합의 독립 검토다.
MoAI는 SPEC·배정·진행 관리 도구다. 작은 교정마다 Pro를 부르지 않는다. 최근 전체
설계 요청 한 건은 완료·회수했고 Astra의 여섯 필수 교정을 반영해 채택했다.
Pro 원문과 Codex/Astra 교정은 저작을 구별한다. 새 Pro 구현 요청은 보내지 않았다.

## 종료 범위와 남은 수

[세부 개발 목록](docs/DEVELOPMENT_ITEMS.md)의 **71개 고유 인도단위**로 종료를 관리한다.
기준 분류는 **개발 및 인수 D 29 / 기존 구현 인수 A 38 / 외부 인수 E 4**다.
이는 같은 크기의 기능 71개나 제품 완료율이 아니다. 기존 소스의 대부분을 재개발한다는
뜻도 아니다. D에 포함된 구현·사용 인수를 다시 별도 A로 더하지 않는다. 기존 44개 부모,
74개 FN, 52개 원요구 절, 22개 Pre 항목, 17개 UC와 다섯 통합장면은 대응 범위이며
개수에 더하지 않는다. 이번 목록의 CLOSED는 아직 선언하지 않았다.
현재 D 29개 중 **5개는 본코드 통합과 한정 확인을 마쳤고, 24개는 추가 개발이 남았다.**
중단 직전의 기능 배정은 아래에 보존한다. 이번 재개는 위 리팩토링 범위이며,
기존 기능 묶음의 작성을 자동 재개한 것은 아니다.
다섯 항목의 미실행 범위와 최종 사용자 인수는 같은 ID 안에서 닫으며 별도 기능으로 더하지 않는다.

각 ID의 입력→조작→결과·단위, 지원 solver/요소/법칙/환경, 수정 코드, 의존,
실패·취소·저장·새 프로세스 재개와 완료조건은 상세 목록 §3–5에 있다.
소프트웨어 인도는 67개 비외부 항목 및 연결된 필수 사용 흐름을 닫으면 종료한다.
나머지 E는 장비 한 건과 승인 SSH/Slurm/OpenPBS 실제 환경 세 건이다.
장비 없이 가능한 수집 경계 개발이나 Windows 배포를 외부 대기로 넘기지 않는다.
공학적 승인·물성·강도·durability UNKNOWN은 프로그램 성공과 별도로 유지한다.
후속 확장을 현재 종료조건에 조용히 더하지 않고, 필수 요구를 미지원 표시만으로 닫지 않는다.

### 중단 전 기능 배정 — 아래 작업은 자동 재개하지 않음

| 담당 | 현재 결과와 쓰기 소유 |
|---|---|
| post_windows_build_fix / Sol-high | 적층 셸 인도 완료. 다음 B6.3.L03: 기존 CCX 지지 반력→정확 TRI6 대응→보존 하중 전달. `_workspace/conservative-load-delivery/`만 작성 |
| inverse_delivery / Sol-high | 스프링·댐퍼 인도 완료. 다음 B1.5.L01: 기존 Aster native hard contact를 사용자 모델의 면 선택·조건·실행·결과에 연결. `_workspace/aster-hard-contact-delivery/`만 작성 |
| dynamic_reprocess_gui / Sol-high | 체결 인도 완료. 다음 B1.4.L02: 기존 native 온도·초기 응력/변형 조건 편집과 실행 연결. `_workspace/initial-fields-delivery/`만 작성 |
| native_post_delivery / Sol-high | 변형률 측도 비교 인도 완료. 다음 B3.3.L01: 고차면 선택과 면 측정. `_workspace/quadratic-surface-delivery/`만 작성 |
| connector_code_review / Sol-high | 관측 불확실성 인도 및 긴 미선택 채널 교정 완료. 현 후보 동결, 새 쓰기 배정 없음 |
| whole_closeout_review / Astra-xhigh | 전체 설계와 E3/E5/E6 통합 독립 검토 완료. 지적 F1–F5 교정 확인, 해당 범위 차단 결함 0 |
| pde_transfer_review / Astra-xhigh | B3.2.L02/B7.3.L01 통합 독립 검토 완료. 행렬 선할당·미선택 채널 간섭 교정 확인, 명시 범위 차단 결함 0 |
| cae_engineering / CAE 자문 | 기존 자문 완료. 다음 native 접촉·초기장·보존 하중·고차면의 필요한 계약만 담당자와 직접 논의. 독립 최종 검토나 제품 Expert와 구별 |
| Codex | Core/registry/owner/public 경계·공통 GUI/저장·문서·Git 통합. 전용 모듈은 담당 작성물을 검토해 반영 |

전용 작성은 각 `_workspace/*-delivery/`에서 분리하고 root가 실제 공통 파일에 병합한다.
담당자들은 구체 설계 문제를 직접 논의할 수 있다. 팀 일곱 개는 소유영역이며 고정 동시
일곱 호출 의무가 아니다. 새 네 항목은 이미 정한 71개 안의 작업이며 범위를 추가한 것이 아니다.

## 이번 체크포인트

- 앞서 게시한 `bb31834`: 완료 native 입력을 새 계산 없이 기존 Simulation 문서로 열고,
  같은 입력 모델을 FreeCAD로 다시 연다. HTTP/CLI/Python/MCP 소스는 같은 문서를 쓴다.
  중복 요청·응답 유실·재시작에서 미저장 편집을 보존하며 공개 data_id 검증 뒤 실행 시 한 번만 해소한다.
- 적층 셸: S8R COMPOSITE 2–16층 입력·층 순서/재료·층별 결과와 실행 메뉴를 제품 트리에
  통합했다. 실제 원 CCX 자료의 DAT 128 IP/FRD 16층 solid를 읽고 FreeCAD·Simulation
  재열기를 확인했다. 원 수집 FAILED는 유지하며 보정 reader의 읽기 성공과 구별한다.
  실제 broker 버튼 전체 왕복과 ParaView 시각화는 아직 수용하지 않았다.
- 스프링·댐퍼: Windows OpenCourant TYPE13·기존 실제 C3D4 FE 영역/RBODY 연결을 통합했다.
  한 실제 Engine 실행에서 힘/모멘트/상대운동 채널을 회수하고 Simulation 재열기와
  원 FreeCAD 계수 편집·저장·새 프로세스 재열기를 확인했다. 일반 implicit static이나
  모든 연결요소 법칙의 지원으로 확대하지 않는다.
- 체결: C3D10의 조임→길이 유지→외력, 절단면 선택과 결과 읽기를 통합했다.
  실제 선택 절단면 절점력 합 599.9996 N은 지지 600 N과 일치한다. SOF −1200.021 N은
  복구 응력 면적분이며 다른 물리량이다. 원값·원 실패를 보존하고 일반 RF/contact force로
  확대하지 않는다. cold 선택의 원 subshape 결속도 같은 원 BRep로 확인한다.
- 세 native 기능의 원 모델 재열기·공개 입력 단일 해소·Ctrl+S/닫기/재연결·미적용 raw
  보관·별도 솔버 메뉴 조건 누락을 교정했다. root 최종 집중 161개 확인 통과, 소유 Job 정리.
  Astra가 실제 반영 소스와 해당 결과를 대조해 다섯 지적을 닫았다. 체결의 새 raw 초안은
  controlled fresh editor에서 확인했으며 실제 새 raw `.caepre` cold 실행으로 바꿔 말하지 않는다.
- 변형률 비교: total E/e/material H를 같은 기준 E로 변환하고 원 측도·행·mask를 유지한다.
  e는 F 필수, E/H는 선택이다. 실제 ParaView 수치 경로·보존본 재열기와 정상/좁은 Qt를
  확인했고 root 37개 집중 확인, 기존 응력/비교 경로 회귀가 통과했다. 사용자 C-bound는
  native 정확도 인증으로 승격하지 않는다.
- 관측 불확실성: 원 교정식·게이지·단축 응력·시간 오프셋을 기존 전파 엔진과 Plan/Study/
  Report에 연결했다. 실제 HTTP 저장·보존본 재열기, root 24개와 후속 2개 경계 확인 및
  QWindows 확인을 마쳤다. 긴 원자료의 N² 선할당과 긴 미선택 채널 간섭을 교정했다.
  두 연구 기능은 Astra의 명시 범위 검토를 마쳤다. 전체 앱의 최종 사용 인수·공학 승인은 별도다.

## 항목별 현재 진도

아래 상태만 현재 작업 목록이다. 개발 대기는 이미 있는 부분까지 없다는 뜻이 아니며,
기존 구현 인수는 기존 자료를 먼저 연결하고 필요한 사용자 경로만 확인한다.
각 행의 구체 완료조건은 같은 ID의 [상세 명세](docs/DEVELOPMENT_ITEMS.md#5-leaf-별-유한한-인도-명세)에 있다.

| ID | 사용자 결과 | 분류 | 현재 상태 | 담당 |
|---|---|---|---|---|
| B1.2.L01 | 다변수 기구·중첩 occurrence 의 마지막 native 인수 | A | 기존 구현 인수 대기 | T1 |
| B1.3.L01 | 곡면·영역별 S8 와 B32R 원출력의 지원 내 왕복 | A | 기존 구현 인수 대기 | T1 |
| B1.3.L02 | B32R native 일반화 회전·완전 지지반력·50IP 관측 완결 | D | 개발 대기 | T1 |
| B1.4.L01 | E3 적층 셸의 층별 입력·출력 | D | 구현 통합·한정 확인 완료 | post_windows_build_fix / Codex |
| B1.4.L02 | E4 온도·초기 응력/변형 상태의 native 편집 | D | 구현 중 | dynamic_reprocess_gui |
| B1.4.L03 | E5 병진·회전 spring/damper | D | 구현 통합·한정 확인 완료 | inverse_delivery / Codex |
| B1.4.L04 | E6 조임→길이 유지→사용 하중 | D | 구현 통합·한정 확인 완료 | dynamic_reprocess_gui / Codex |
| B1.5.L01 | C1 진짜 hard 접촉 | D | 구현 중 | inverse_delivery |
| B1.5.L02 | C2 implicit cohesive 와 압축 재접촉 | D | 개발 대기 | T2 |
| B1.5.L03 | C3 곡면·모서리·연쇄 tie 조정 | D | 개발 대기 | T2 |
| B1.5.L04 | C5 단계 활성과 접합 해제의 native 상태 연속 | D | 개발 대기 | T2 |
| B1.5.L05 | C4 small/large sliding 과 실제 법선·쌍 교환 | D | 개발 대기 | T2 |
| B1.5.L06 | C6 병진·회전 주기 경계의 지원 내 인수 | A | 기존 구현 인수 대기 | T2 |
| B1.6.L01 | 새 implicit 조합의 pair 장·합력·기준점 모멘트 | D | 개발 대기 | T2 |
| B1.6.L02 | 기존 J2+기하+linear/Coulomb 접촉 사용자 인수 | A | 기존 구현 인수 대기 | T2 |
| B1.6.L03 | S2 Code_Aster 사용자 모델의 비선형 실행 | D | 개발 대기 | T2 |
| B2.1.L01 | U/V·밀도·감쇠의 실제 초기 상태 | A | 기존 구현 인수 대기 | T2 |
| B2.2.L01 | 정적 preload→동적 상태 carry | A | 기존 구현 인수 대기 | T2 |
| B2.3.L01 | 시간 stream·부분 실패·명시 재후처리 | A | 기존 구현 인수 대기 | T2 |
| B2.4.L01 | Windows WRITE→READ 실제 restart | A | 기존 구현 인수 대기 | T2 |
| B2.5.L01 | 계층 INP 의 기존 flat 물리 범위 합류 | D | 개발 대기 | T2 |
| B2.5.L02 | native RAD 의 LAW36/INIEVO·LAW117 명시 편집 | D | 개발 대기 | T2 |
| B2.6.L01 | LAW36/INIEVO 실제 손상·삭제·에너지 인수 | A | 기존 구현 인수 대기 | T2 |
| B2.6.L02 | LAW117 부분 손상 unload–compression–reopen | D | 개발 대기 | T2 |
| B2.6.L03 | 완전 삭제 후 bulk-face 재접촉·재개구 | D | 개발 대기 | T2 |
| B2.6.L04 | pair force·표본 impulse·질량·에너지의 최종 선택 연결 | A | 기존 구현 인수 대기 | T2 |
| B2.6.L05 | 기존 ε–N·SWT·critical-plane 피로의 실제 작업 인수 | A | 기존 구현 인수 대기 | T2 |
| B3.1.L01 | 실제 ParaView 주창·선택 설정의 OS 작업 인수 | A | 기존 구현 인수 대기 | T3 |
| B3.1.L02 | managed ParaView 저장·File→Exit 네 경로 | A | 기존 구현 인수 대기 | T7 |
| B3.2.L01 | 네 원응력→공통 Cauchy 비교 | A | 기존 구현 인수 대기 | T3 |
| B3.2.L02 | 변형률의 유한한 측도 비교 | D | 구현 통합·한정 확인 완료 | native_post_delivery |
| B3.2.L03 | TET/HEX 고차 공간 비교 | D | 개발 대기 | T3 |
| B3.3.L01 | 고차면 측정 | D | 구현 중 | native_post_delivery |
| B3.3.L02 | 다중 block 측정·원 leaf 복귀 | D | 개발 대기 | T3 |
| B3.3.L03 | 실제 현재 형상 면적·법선으로 측정 | D | 개발 대기 | T3 |
| B3.4.L01 | 원 결과 복구·변경 branch·정확한 원 선택 반환 | A | 기존 구현 인수 대기 | T3 |
| B4.1.L01 | 처리 recipe·재표본 계보·큰 Data 작업 인수 | A | 기존 구현 인수 대기 | T4 |
| B4.2.L01 | 단축·동축 유한변형 관측→같은 측도 예측 | A | 기존 구현 인수 대기 | T4 |
| B4.3.L01 | 혼합 F/stress 제어의 법칙별 인수 | A | 기존 구현 인수 대기 | T4 |
| B4.4.L01 | 후보 상세 보존·새 평가·채택 충돌 | A | 기존 구현 인수 대기 | T4 |
| B4.5.L01 | 사례 A: 기존 J2 와 DP 의 같은 물리시험 비교 | A | 기존 구현 인수 대기 | T4 |
| B4.5.L02 | 사례 C 의 다영역 열·점탄성 FE 경로 | D | 개발 대기 | T4 |
| B5.1.L01 | 혼합변수 DOE 의 실제 domain binding | A | 기존 구현 인수 대기 | T5 |
| B5.3.L01 | 일반 역해석의 고정 관측·feasible 후보 왕복 | A | 기존 구현 인수 대기 | T5 |
| B5.4.L01 | 필수 사례별 미분법 선택·기존 adjoint 인수 | A | 기존 구현 인수 대기 | T5 |
| B5.6.L01 | 보존 대리모델·다목적·Picard/MDO 한 정의 | A | 기존 구현 인수 대기 | T5 |
| B6.1.L01 | 사용자 MFront→한 실제 FE interface | D | 개발 대기 | T4 |
| B6.1.L02 | 구성식 increment·접선·FE IP 원값 인수 | A | 기존 구현 인수 대기 | T4 |
| B6.2.L01 | 독립 PDE 의 선언 모델별 입력·실제 해·재개 | A | 기존 구현 인수 대기 | T5 |
| B6.3.L01 | 변위 vector → 구조 Dirichlet port | D | 개발 대기 | T5 |
| B6.3.L02 | 초기 응력 tensor port | D | 개발 대기 | T5 |
| B6.3.L03 | CCX 고정 지지 RF 에서 다른 C3D10 경계로 보존 하중 전달 | D | 구현 중 | post_windows_build_fix |
| B6.3.L04 | 기존 P1 온도에서 3D 이중층·계면까지 | D | 개발 대기 | T5 |
| B7.1.L01 | 문헌 원문·독립 Study·판단 보존 | A | 기존 구현 인수 대기 | T6 |
| B7.2.L01 | 기존 3 역할 Expert 의 중단·한도·부분응답 재개 | A | 기존 구현 인수 대기 | T6 |
| B7.3.L01 | B−A 비교 불확실성 | D | 구현 통합·한정 확인 완료 | connector_code_review |
| B7.4.L01 | 기존 robust/DE 최종 perturbation→다음 시험 | A | 기존 구현 인수 대기 | T6 |
| B7.5.L01 | 실제 3D 장면·판단·수치가 들어간 한 보고서 | A | 기존 구현 인수 대기 | T6 |
| B7.6.L01 | 장비 없이 닫는 공통 취득·sequence·종료 소프트웨어 | D | 개발 대기 | T6 |
| B7.6.L02 | 실제 장비 한 종류의 binding·권한·물리 stop 인수 | E | 외부 입력 대기 | T6 |
| B8.1.L01 | 모든 독립 앱·파일의 정확 owner 열기 | A | 기존 구현 인수 대기 | T7 |
| B8.2.L01 | 여러 owner 의 편집·부분저장·복구초안 | A | 기존 구현 인수 대기 | T7 |
| B8.3.L01 | 이동 사본 전체 선언 문서의 cold 편집 | A | 기존 구현 인수 대기 | T7 |
| B8.4.L01 | 외부 batch·remote 공통 소프트웨어 계약 인수 | A | 기존 구현 인수 대기 | T2 |
| B8.4.L02 | SSH 직접 실행 실제 승인 호스트 인수 | E | 외부 입력 대기 | T2 |
| B8.4.L03 | Slurm 실제 승인 호스트 인수 | E | 외부 입력 대기 | T2 |
| B8.4.L04 | OpenPBS 실제 승인 호스트 인수 | E | 외부 입력 대기 | T2 |
| B8.5.L01 | 연결 graph/list·관계 수정의 실제 GUI 왕복 | A | 기존 구현 인수 대기 | T7 |
| B8.6.L01 | 새 Windows PC 설치·native 발견·소스/라이선스 폐쇄 | A | 기존 구현 인수 대기 | T7 |
| B8.6.L02 | GUI/CLI/Python/MCP 동일 명령·owner | A | 기존 구현 인수 대기 | T7 |
| B8.6.L03 | 전체 앱의 종료 가능한 실제 사용 동선 | A | 기존 구현 인수 대기 | T7 |

## 다음 행동

1. 새 네 인도의 확정 profile과 기존 구현을 해당 ID에서 읽고 전용 본코드를 병렬 작성한다.
   native 메뉴·reader·기존 JobManager/owner를 재사용하고 공통 파일은 root가 순차 병합한다.
   일반 코드와 작은 교정의 Pro 호출은 없다.
2. 이번 다섯 기능은 재개발하지 않는다. 미실행 사용자 경로는 해당 항목/최종 통합장면에서
   기존 자료를 재사용해 닫는다. 다른 항목의 선행조건으로 unchanged solver 캠페인을 반복하지 않는다.
3. 각 인도의 코드·한국어 사용법·필요한 최소 확인을 함께 커밋·push하고 원격을 확인한다.
   사용 차단 결함은 같은 ID에서 교정하며, 후속 확장을 조용히 추가하지 않는다.
4. Windows SDK CI는 호스팅 runner 통신 단절로 실패했다. 로그 ZIP·artifact·해당 draft
   release가 없어 회수/증분 재개는 불가능했다. 구체 자원 원인을 추정해 SDK를 바꾸거나
   같은 긴 빌드를 자동 반복하지 않는다. stock ParaView 사용을 막지 않는다. 배포·새 PC 인수는 남는다.

## 기준 소스·보존·관련 자료

- 상세 종료목록 게시: `6de7c44`. native 세 기능 통합: `e2c2e43`.
  두 연구 기능과 이 현재상태는 이번 연구 통합 커밋에 포함한다. 실제 HEAD/원격은 새 세션에서
  Git으로 확인하며, 로컬 커밋과 원격 게시를 구별한다.
- pinned upstream: `plugins/fixture_design/upstream`의
  `3e48bf6138f495299f45b1af254bfb4aaff307b8`, 변경 없음.
- 사용자 미추적 자료 `.codex-remote-attachments/`,
  `docs/images/manual/evaluation-case02-draft.png`는 보존하고 이번 커밋에 넣지 않는다.
- MoAI 실제 MCP SPEC 목록 14개를 확인했다. 기존 t3/t25 카드를 사용하며 이 문서와
  경쟁하는 별도 진도표를 만들지 않는다. 주어진 모델·무료 사용권·기존 설정을 유지한다.
- 실제 Pro 전체 원문·Astra 검토·원 자료는 `_workspace/closeout-20261016/`에 보존했다.
  공개 개발 범위는 `docs/DEVELOPMENT_ITEMS.md`이고 전달 회수 기록은 제품 결과가 아니다.
- 실제 native 한정 자료·원 실패·프로세스 정리는 각 `_workspace/native-*-delivery/`에 있다.
  `_workspace/`는 공개 배포 파일이 아니다. 필요한 공개 원 fixture·사용법은 제품 docs/tests에 둔다.
- [한국어 설치](docs/INSTALL_KO.md), [첫 사용](docs/USER_GUIDE_KO.md),
  [후처리](docs/native-project/POST_KO.md), [적층 셸](docs/composite-shell/USAGE_KO.md),
  [체결 하중](docs/PRETENSION_KO.md), [스프링·댐퍼](docs/CONNECTOR_KO.md),
  [변형률 비교](apps/research/POST_NUMERICAL.md),
  [관측 불확실성](docs/experiment_expert/OBSERVATION_UNCERTAINTY_KO.md),
  [기존 실행계획](docs/IMPLEMENTATION_DELIVERIES.md).
- 이전의 누적 상태 원문은 [보존본](docs/history/20261016-before-closeout/CURRENT_STATE.md)에
  바이트 그대로 남겼다. 그 안의 옛 담당·다음 행동·견적은 현재 작업 지시가 아니다.
  기존 실패·측정값·허용치와 유효한 계약/ADR은 해당 원기록을 계속 따른다.
