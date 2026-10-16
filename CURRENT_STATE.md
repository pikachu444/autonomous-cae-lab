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

사용자는 개발을 계속하라고 승인했고 Goal은 active다. 개발 중에는 영향을 받은 최소
실행·단위 확인을 수행하며 변경하지 않은 솔버 캠페인을 반복하지 않는다. 테스트로 연
프로그램은 해당 Windows Job/PID만 정리한다. 사용자 세션을 이름으로 종료하지 않는다.
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

각 ID의 입력→조작→결과·단위, 지원 solver/요소/법칙/환경, 수정 코드, 의존,
실패·취소·저장·새 프로세스 재개와 완료조건은 상세 목록 §3–5에 있다.
소프트웨어 인도는 67개 비외부 항목 및 연결된 필수 사용 흐름을 닫으면 종료한다.
나머지 E는 장비 한 건과 승인 SSH/Slurm/OpenPBS 실제 환경 세 건이다.
장비 없이 가능한 수집 경계 개발이나 Windows 배포를 외부 대기로 넘기지 않는다.
공학적 승인·물성·강도·durability UNKNOWN은 프로그램 성공과 별도로 유지한다.
후속 확장을 현재 종료조건에 조용히 더하지 않고, 필수 요구를 미지원 표시만으로 닫지 않는다.

### 현재 병렬 배정

| 담당 | 현재 결과와 쓰기 소유 |
|---|---|
| post_windows_build_fix / Sol-high | 적층 셸: 층 편집·native 입력·층별 S/E·재편집. 전용 후보 동결, root가 제품 통합. 공통 파일 직접 쓰기 없음 |
| inverse_delivery / Sol-high | 스프링·댐퍼: 실제 FE 영역 연결·축/계수·Windows native 응답·저장재개. 전용 후보 동결, root가 통합 |
| dynamic_reprocess_gui / Sol-high | 체결: 절단면/축·조임/유지/외력·결과. 전용 후보 동결, 선택 원결속의 작은 공통 교정 제안 중 |
| native_post_delivery / Sol-high | 변형률 측도 비교: E/e/H의 명시 변환·원 측도/마스크·Post 선택/저장 흐름. 전용 private 소스 작성 |
| connector_code_review / Sol-high | 교정식·게이지·시간 오프셋의 1차 불확실성 연결. 기존 엔진·Plan/Study 재사용, 전용 private 소스 작성 |
| whole_closeout_review / Astra-xhigh | 전체 종료설계 독립 검토 완료. 현재 E3/E5/E6의 통합 소스·실제 결과·창·실패/복구를 읽기 전용 검토 |
| cae_engineering / CAE 자문 | 고정 원문/실제 진단으로 요소·물리량·변형률 계약 자문 완료. 제품 Expert 기능이나 독립 통합 PASS와 구별 |
| Codex | Core/registry/owner/public 경계·공통 GUI/저장·문서·Git 통합. 전용 모듈은 담당 작성물을 검토해 반영 |

전용 작성은 각 `_workspace/*-delivery/`에서 분리하고 root가 실제 공통 파일에 병합한다.
담당자들은 구체 설계 문제를 직접 논의할 수 있다. 팀 일곱 개는 소유영역이며 고정 동시
일곱 호출 의무가 아니다. 현재 세 native 기능과 두 연구 기능을 병행한다.

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
  확대하지 않는다. cold 선택의 원 subshape 결속 교정이 남아 있다.
- 현재 root 집중 확인: 첫 통합 확인에서 86개가 통과했다. 이후 닫힌 원 모델 재열기,
  public 입력의 단일 해소, 기존 S8 저장 대역을 교정하고 해당 확인이 통과했다.
  Astra가 찾은 미적용 값의 Ctrl+S/닫기/재연결 보관과 솔버 메뉴의 조건 누락은 같은
  기능에서 교정 중이다. 제품 전체 인수나 실제 물리 적격성 통과로 표시하지 않는다.

## 항목별 현재 진도

아래 상태만 현재 작업 목록이다. 개발 대기는 이미 있는 부분까지 없다는 뜻이 아니며,
기존 구현 인수는 기존 자료를 먼저 연결하고 필요한 사용자 경로만 확인한다.
각 행의 구체 완료조건은 같은 ID의 [상세 명세](docs/DEVELOPMENT_ITEMS.md#5-leaf-별-유한한-인도-명세)에 있다.

| ID | 사용자 결과 | 분류 | 현재 상태 | 담당 |
|---|---|---|---|---|
| B1.2.L01 | 다변수 기구·중첩 occurrence 의 마지막 native 인수 | A | 기존 구현 인수 대기 | T1 |
| B1.3.L01 | 곡면·영역별 S8 와 B32R 원출력의 지원 내 왕복 | A | 기존 구현 인수 대기 | T1 |
| B1.3.L02 | B32R native 일반화 회전·완전 지지반력·50IP 관측 완결 | D | 개발 대기 | T1 |
| B1.4.L01 | E3 적층 셸의 층별 입력·출력 | D | 제품 통합·확인 중 | post_windows_build_fix / Codex |
| B1.4.L02 | E4 온도·초기 응력/변형 상태의 native 편집 | D | 개발 대기 | T1 |
| B1.4.L03 | E5 병진·회전 spring/damper | D | 제품 통합·확인 중 | inverse_delivery / Codex |
| B1.4.L04 | E6 조임→길이 유지→사용 하중 | D | 제품 통합·확인 중 | dynamic_reprocess_gui / Codex |
| B1.5.L01 | C1 진짜 hard 접촉 | D | 개발 대기 | T2 |
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
| B3.2.L02 | 변형률의 유한한 측도 비교 | D | 구현 중 | native_post_delivery |
| B3.2.L03 | TET/HEX 고차 공간 비교 | D | 개발 대기 | T3 |
| B3.3.L01 | 고차면 측정 | D | 개발 대기 | T3 |
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
| B6.3.L03 | CCX 고정 지지 RF 에서 다른 C3D10 경계로 보존 하중 전달 | D | 개발 대기 | T5 |
| B6.3.L04 | 기존 P1 온도에서 3D 이중층·계면까지 | D | 개발 대기 | T5 |
| B7.1.L01 | 문헌 원문·독립 Study·판단 보존 | A | 기존 구현 인수 대기 | T6 |
| B7.2.L01 | 기존 3 역할 Expert 의 중단·한도·부분응답 재개 | A | 기존 구현 인수 대기 | T6 |
| B7.3.L01 | B−A 비교 불확실성 | D | 구현 중 | connector_code_review |
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

1. 세 native 기능의 마지막 연결·선택 보호 교정을 통합하고, 변경된 경로만 확인한다.
   정상/좁은 실제 창과 단위·선택·실패/취소·원 모델 재편집을 대조한다. Astra의 실제
   blocking 지적을 같은 기능에서 닫고, 미실행 범위는 남긴다.
2. 변형률 비교와 관측 불확실성의 작성물을 병행 회수·통합한다. 공통 파일은 root가
   순차 병합하고 새 수치 엔진/저장소를 만들지 않는다.
3. 검토한 묶음을 커밋·push하고 원격 반영을 확인한다. 71개 목록의 같은 ID에서
   상태를 갱신한 뒤 기존 의존 순서에 따라 다음 개발을 배정한다. 작은 교정 Pro 호출은 없다.
4. Windows SDK CI는 실패 종료했다. 기존 담당이 해당 로그의 종료 원인과 한정 대안을
   조사하며 새 실행을 자동으로 반복하지 않는다. 배포 성공·새 PC 수용은 미완료다.
   stock ParaView 사용은 해당 SDK를 기다리지 않는다.

## 기준 소스·보존·관련 자료

- 마지막 게시 기준: main `bb318346c81ae6ca3d0b32494363778ae770e1b8`.
  이번 E3/E5/E6 통합·목록은 아직 작업 트리이며 게시 확인 후 이 항목을 갱신한다.
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
  [체결 하중](docs/PRETENSION_KO.md), [기존 실행계획](docs/IMPLEMENTATION_DELIVERIES.md).
- 이전의 누적 상태 원문은 [보존본](docs/history/20261016-before-closeout/CURRENT_STATE.md)에
  바이트 그대로 남겼다. 그 안의 옛 담당·다음 행동·견적은 현재 작업 지시가 아니다.
  기존 실패·측정값·허용치와 유효한 계약/ADR은 해당 원기록을 계속 따른다.
