# 세부 개발 목록과 지원 범위

기준: 2026-10-16, 공개 main `bb31834`와 통합된 `e76cde6` 변경. 기능 범위·지원 조합·종료조건을 정하는 인도목록이다. 최신 담당·상태는 [CURRENT_STATE.md](../CURRENT_STATE.md) 한 곳을 따른다.

저작 이력: Pro 원안 `_workspace/closeout-20261016/pro-result/whole-product-closeout.md`는 수정하지 않고 보존했다. 이 통합본은 그 원안에 Astra R1–R6 검토와 Codex가 확정한 여섯 교정을 반영한 편집본이며, Pro의 재작성 결과와 구별한다. 원안의 상세 archive/ZIP/hash/AST/테스트 개수는 제품 계획에 옮기지 않는다.

기준 대조: Pro 원안의 기준 commit 은 `8c1d264`다. 현재 main `bb31834`와 `e76cde6` 구현을 대조해 기존 기능의 중복 배정을 제거했다. 상태표가 아니며 후보·private 작성·실제 수용은 서로 구분한다.

## 1. 결론과 계수

71개 고유 인도단위를 유지한다. **D 29개**는 개발 및 인수, **A 38개**는 구현이 있으며 정확한 사용자 결과의 인수·기록 대조가 남은 단위, **E 4개**는 실제 장비 1 개와 승인 원격 host 3 개의 외부 인수다. **D+A=67개 소프트웨어**, 전체 종료 분모는 71 개다. 44개 부모, 74개 FN, Pre22, 17개 UC, 다섯 통합장면과 7개 팀은 추적·수용 범위이며 분모에 더하지 않는다. 기존 52개 원요구 절도 기능 분모가 아니다. 완료율은 제시하지 않는다.

각 leaf 는 D/A/E 중 하나만 가진다. A 에서 필수 코드 누락이 발견되면 같은 ID 를 D 로 재분류하고 합계 71 은 유지한다. 한 사용자 결과의 개발·수용·저장·재개를 여러 기능으로 세지 않는다.

### 전체 종료식

`CLOSED = 실제 입력/편집 가능 ∧ 지정 backend·계산·명령 연결 ∧ 물리량/단위/원자료 일치 ∧ 정상 결과 선택 ∧ 대표 실패·취소/재시도 보존 ∧ 저장/새 프로세스 재개 ∧ 관련 최소 검증 ∧ 공개 예제/한국어 사용법/현재 main 게시 일치`

`SOFTWARE_CLOSED = 모든 67개 비외부 leaf CLOSED ∧ 필수 설계미결 0 ∧ 데이터손실/물리량오해/중복실행/사용차단 결함 0 ∧ 44 부모·74 FN·Pre22·17 UC 누락 0 ∧ 다섯 통합장면 수용`

`FULLY_CLOSED = SOFTWARE_CLOSED ∧ 네 E leaf 의 실제 연결·허용 동작·종료 수용`

소프트웨어만 닫힌 경우 “명시한 소프트웨어 인도 범위 완료, 장비·원격 실환경 인수 미완료”라고 보고한다. 공학적 승인, 재료 교정 부족, durability 의 UNKNOWN/NOT_RELEASED 는 프로그램 인수와 별도다.

## 2. 실제 근거와 우선순위

최신 사용자 지시와 root 가 확정한 교정, 이 인도목록, 원요구·SPEC/acceptance, 공개 제품 소스·검사, 고정 upstream 순으로 대조한다. 현재 진행은 [CURRENT_STATE.md](../CURRENT_STATE.md)가 유일하게 소유한다. ZIP 의 전수 파일·함수·테스트 통계는 실행/수용 증거가 아니므로 지원 계획의 근거로 쓰지 않는다.

독립 도구 Data·Material·PDE·Numerical·Runner·Expert·Study, FreeCAD CAD/FE, 실제 ParaView Post 와 선택 Workbench 를 유지한다. 일상 GUI·Python·CLI 사용은 작업에 필요하지 않은 CAD·AI·OpenScience·MCP 를 전제하지 않는다. 기존 reader, numerical engine, JobManager, 문서 owner 와 pinned upstream 을 adapter 를 통해 재사용한다. 실패·취소·원입력·기존 결과·UNKNOWN 을 성공처럼 바꾸지 않는다.


## 3. 전체 지원 범위를 고정하는 선택

아래 profile 은 **현재 구현**과 **이번에 구현할 필수 목표**를 구별한다. 지원 목록은 profile 의 합집합이지 모든 solver×element×law×OS 의 곱집합이 아니다. 모든 D 가 실제 수용되기 전 목표 조합을 현재 “지원됨”으로 표시해서는 안 된다.

Aster/MFront/FEniCSx 의 기존 선택적 Linux worker 는 Windows Qt 에서 입력/보존/결과를 다룬다는 뜻이지 그 solver 가 Windows native 라는 뜻이 아니다. WSL 을 모든 앱의 전제조건으로 만들지 않는다. 동시에 Aster 전용 계산을 기존 Linux worker 도 없이 Windows native 로 실행할 수 있다고 말하지 않는다. 그 profile 의 설치/계산 환경과 수용은 별도로 표시한다. 새 유료 호스트를 조달하지 않는다.

특히 CCX 출력 전용 관측 build, Aster hard/cohesive 및 각 요소의 정확 native 조합은 이 설계만으로 지원을 인증하지 않는다. 연결요소는 선정한 Windows OpenCourant 경로를 사용한다. 사용자가 요구한 결과를 만족시키는 **유한한 개발 목표**로 선택했다. 고정 소스의 card/catalog 와 작은 native 실행 확인이 해당 D 의 첫 구현 단계이며, 입증 실패를 UNKNOWN 표시만 남기고 완료 처리하는 방법은 없다.

### 3.1 세 필수 사용자 사례에 대한 결론

**A — J2 와 명시 DP 의 재료점·FE/holdout 비교:** 기존 Material/fit 와 CCX J2·FELUPE DP FE 를 사용한다. 실제 시험 원행/관측량이 같아야 하며 mesh 가 다르면 명시 ROI/측도 mapping 을 쓴다. 원 시험에서 재료와 지그 효과를 구별하지 못하면 그 판단은 UNKNOWN 이나, 비교·저장·식별 진단·다음시험 기록 workflow 는 완료해야 한다.

**B — 지그 강성·마찰·체결·편심:** 기존 M4/기하·메시·탄성/J2 와 periodic/linear contact 를 유지하고 필요한 spring/damper·pretension·진짜 hard/contact 조합을 추가한다. 단면 rigid-fit 회전을 native rotation 으로 승격하지 않는다. 같은 두점 gauge 를 실측/해석에 사용하고 후보를 원 CAD 에 자동 적용하지 않는다.

**C — 열 곡률·계면 손상·재닫힘·점탄성 회복:** P1 온도장→명시 z-extruded 3D bilayer 의 T/Tref 전달, 기존 FE 의 두 영역 thermal/Maxwell 응답, Aster HEXA8/CZM_LIN_REG 계면 경로 및 실제 관측시각 비교를 연결한다. 한 모델이 모든 법칙을 동시에 가져야 한다고 요구하지 않지만, solver·단계·전달량이 명시된 같은 평가 정의에서 연결되어야 한다. 별개 데모 네 개를 나란히 놓는 것으로 통합 성공을 세지 않는다.

### 3.2 비온도 전달과 미분의 끝점

비온도 전달은 네 범용 field engine 이 아니라 U→다른 mesh prescribed U, 동일 mesh/IP σ→탄성 초기상태, native 한쪽 nodal force→보존하중 Hᵀ의 세 port 로 고정한다. 기존 온도 port 의 Case C 3D receiver 를 네 번째 leaf 로 둔다. 힘 보존과 온도/응력 보존을 같은 기준으로 검사하지 않는다.

미분은 기존 선형 scalar P1 adjoint, 명시 ordinary-residual FD, 필수 시간/형상/연성 탐색의 기존 derivative-free 를 각각 배치한다. 비선형 교정 불확실성은 실제 관측점의 1차 JΣJᵀ와 적용범위 고지로 고정한다. 최종점 식별성은 보존된 ordinary-residual FD/SVD 의 국소 진단이지 통계적 profile likelihood 나 전역 식별 보장이 아니다. 이는 원 FN05/21·EXPERIMENT/NUMERICAL 의 허용을 좁은 예제로 삭제하거나 네 범용 adjoint 로 확대한 선택이 아니다.

### 3.3 정확 profile 목록
#### W — 공통 인수 환경

Windows x64 로컬 제품. 새 PC 인수 기준은 Windows 11 x64 한 실제 OS build 와 1440×900/1920×1080, 좁은 창 및 기존 지정 DPI 다. Research 는 기존 Python/PySide6 배포를 그대로 사용한다. 브라우저·WSL·CAD·AI·MCP 는 일상 Data/Material/Numerical/Study/Report 작업의 필수조건이 아니다. native 프로세스와 Research 프로세스를 합치지 않는다.

**수용 경계:** Python/PySide6 의 숫자 버전·lock/배포 스크립트는 이 ZIP 만으로 고정할 수 없다. 기존 배포 lock+실행파일 SHA+실제 OS build 를 B8.6.L01 에 회수해 잠근다. 임의 최신 버전을 골라 지원했다고 하지 않는다. 이는 소프트웨어 인수 A 이지 외부조건 E 나 무한 호환성 작업이 아니다.
#### PRE — 기존

FreeCAD 1.1.4 native Part/Assembly/FEM, 기존 Gmsh 경로, FCStd/메시/재료·조건 참조. M4 의 선택 occurrence→독립 편집 FE 모델과 native 기하/메시 생성은 재사용한다. geometry/mesh/조건 identity 가 변경되면 명시 re-freeze/새 실행이며 옛 결과는 보존한다.

**수용 경계:** Gmsh 바이너리의 숫자 버전은 첨부에서 확정하지 못했다. 기존 launcher 선택과 실제 version/hash 를 배포 인수에서 기록한다. Gmsh·CAD kernel 을 새로 작성하는 leaf 는 없다.
#### POST — 기존

ParaView 6.2 native 가 3D·필터·선택·시간·Render/Spreadsheet/XYChart 의 주 창이다. Qt Post 는 별도 비모달 선택 설정창이다. 외부 VTU/PVD 와 기존 등록 결과, 실제 block leaf/행/성분/시각을 사용한다. 정적 그림을 3D 라고 부르지 않는다.

**수용 경계:** 현재 source 의 bridge/Workspace/명령·저장과 stock ParaView 를 재사용한다. native SDK 플러그인과 stock 사용을 별도 profile 로 나눈다.
#### POST-SDK — 구현·패키징 인수

ParaView 6.2 와 정확히 호환되는 기존 managed-close 플러그인. File→Save/Exit, Ctrl+S, Ctrl+W, 창 X/Alt+F4 에서 같은 owner 의 미적용/dirty/부분저장/응답 미확인 처리를 연결한다. Qt 보조창 닫기와 native owner 종료는 별개다.

**수용 경계:** 해당 SDK artifact 의 ABI·runtime·hash 와 설치 후 실제 입력을 B3.1.L02 에서 확인한다. 첨부의 진행 중 CI 는 현재 성공 증거가 아니다. SDK 없이도 stock ParaView 기본 열기·계산·결과 보기는 계속된다.
#### MOTION — 기존

FreeCAD 1.1.4 Revolute/Slider/Cylindrical 의 지원 DOF 와 bounded motion expression. time/pi, 상수·명시 변수, +/−/×/÷, sin/cos/arctan 과 차원·의존 DAG 를 현재 validator 가 허용하는 범위로 사용한다. 반복 occurrence 는 하나의 정확 경로로 선택한다. 기본 종속식/4절 기구/M4 를 재개발하지 않는다.

**수용 경계:** 현재 motion_relation/motion_formula 의 수·식 길이 제한이 입력 계약이다. 그 제한의 임의 증대, 임의 Python 식, 모든 Assembly joint 조합의 곱집합은 이번 종료조건이 아니다.
#### CCX-STATIC — 기존

CalculiX 2.22, C3D10 3D solid, 등방 선형탄성 및 기존 J2 등방경화 소성표, 지원 NLGEOM 와 기존 linear pressure-overclosure/Coulomb contact. native U/S/E/PE·수렴·실패와 원 입력을 보존한다. 기본 단위계는 mm–N–s–Mg, MPa 와 N·mm 이며 원 입력 단위를 명시 변환한다.

**수용 경계:** 기존 NS1/native 입증을 유지한다. 다른 요소·고급 접촉·DP 를 이 CCX profile 에 자동 승격하지 않는다. native 실행 성공, 수치 타당성, 공학 승인도 별개다.
#### CCX-SHELL — 기존

CalculiX 2.22 S8, 양의 두께, 기준면/offset/법선, 평면 및 현재 구현된 곡면·영역별 두께/압력. 상·하면과 원 native 확장요소/적분점·.12d/FRD/DAT 대응을 보존한다.

**수용 경계:** 동일 구역 0 압력은 허용하되 전체 무하중 차단·coverage·부호·재번호·형상 변경 gate 를 유지한다. 균질 S8 를 적층 shell 이라고 하지 않는다.
#### CCX-BEAM — 기존

CalculiX 2.22, 직선·균일 RECT B32R. 단면 치수와 국부축, 병진/회전 조건, 끝 힘·모멘트. section forces 의 명시 출력과 OUTPUT=3D raw-stress 출력을 다른 실행 선택으로 유지한다. raw 50IP S/E/COORD 는 실제 존재·정체성 확인분만 제공한다.

**수용 경계:** 기존 rigid-fit 회전, FRD RF 합, stress-traction 적분 모멘트는 derived 로 유지한다. 원 일반화 DOF/모든 constraint reaction 과 동일하다고 바꾸지 않는다.
#### CCX-BEAM-OBS — 선정한 필수 개발 목표

같은 CCX-BEAM 모델에서 실제 생성된 mean-rotation MPC/knot의 일반화 좌표와 공액 반력, 소거/복원 기여, 모든 선택 지지집합의 합력·기준점 모멘트, 원 IP COORD/S/E를 관측한다. 모든 원 beam 절점에 독립 회전 3DOF가 있다고 가정하지 않는다. 그 밖의 단면 회전은 유도값으로 구별한다. 관측을 위해 knot나 구속을 추가하지 않으며, 실제 소스 변수와 출력 대응을 확정하는 것이 첫 구현 단계다. 기존 2.22의 출력이 부족할 때만 같은 소스의 출력 전용 build를 별도 선택지로 제공한다. 요소·적분·물리 알고리즘은 바꾸지 않는다.

**수용 경계:** 관측 build 는 자동 pin 교체가 아니며 사용자가 명시 선택하는 같은 솔버의 추가 산출물이다. 실제 native 소스·출력 위치는 ZIP 밖이므로 수정됐다고 주장하지 않는다. source 위치·구속 work conjugacy·native 결과 검증과 무료 재배포 조건까지 B1.3.L02/B8.6.L01 에서 닫는다. 숫자 채널이 없다는 문구만으로 이 요구를 닫지 않는다.
#### CCX-LAMINATE — 선정한 필수 개발 목표

CalculiX 2.22 S8R COMPOSITE 한 profile. 2–16층, 층별 선형 직교이방 재료·두께·각도·순서, 양의 총두께와 명시 shell 기준면. 각 층의 원 IP·상하 위치·S/E 를 선택한다. 기존 S8 균질 profile 과 구분한다.

**수용 경계:** 층수 16 은 이번 편집·인수의 유한 상한이며 모든 laminate law/solid-shell 개발이 아니다. 실제 2.22 card/층출력 조합은 B1.4.L01 에서 고정 소스와 작은 native 실행으로 먼저 수용한다. 원물성 없이 등가 등방값을 넣지 않는다.
#### INIT-THERMAL — 선정한 필수 개발 목표

온도: CCX 2.22 C3D10 등방 탄성, nodal T/Tref·α와 온도 절대값/증분 구분. 초기 응력: 같은 CCX 요소·native IP 의 6 성분 small-strain 탄성 σ0. 초기 변형 상태: Code_Aster 17.4 TETRA10 의 호환 affine u0/ε0 및 일치하는 σ0 를 ETAT_INIT 의 실제 변위·응력 상태로 설정한다. 임의 eigenstrain·plastic internal state 를 σ0 하나에서 복원하지 않는다.

**수용 경계:** 기존 dynamic U/V, P1 온도 전달과 같은 단위/기저 계약을 재사용한다. ε0 는 독립 초기 plastic-strain 카드의 별칭이 아니다. 비호환 상태는 저장 가능하되 해당 계산을 막는다. 원 E4 가 필요한 온도·초기 stress/strain 의 세 선택을 모두 실제 native 초기 상태로 보여야 닫는다.
#### CONNECTOR — 선정한 필수 개발 목표

주 지원 경로는 기존 Windows OpenCourant pin `cb760c2`의 TYPE13 선형 connector 와 실제 elastic C3D4 FE patch/RBODY attachment 다. 병진·회전 6대각 k/c, 단위·오른손 국부축, 실제 질량·관성 및 native 일반화 상대운동을 보존한다. 기존 FE 변형체와 하중 전달을 유지하고 지원 explicit transient 를 실행한다.

**수용 경계:** CCX 병진 및 Code_Aster 회전 조합은 비교 대안이며 둘 다 새 필수 작업으로 요구하지 않는다. TYPE13 을 독립 Aster 6DOF spring, implicit static, ideal massless 또는 0-length connector 와 동등하게 표현하지 않는다. 일반 6×6 연성 행렬과 비선형/파손 connector 는 범위 밖이다.

#### CCX-PRETENSION — 선정한 필수 개발 목표

CalculiX 2.22 C3D10 직선 볼트 한 절단면/명시 축과 native PRE-TENSION SECTION. 조임 force 또는 displacement→현재 길이 유지→사용 외력→제하, 최대 네 단계. 탄성/J2 등방경화와 기존 허용 접촉만.

**수용 경계:** 나사산 세부 접촉·토크/마찰계수에서 조임력 역산은 이 요구의 자동 기능이 아니다. 사용자가 입력한 조임력과 실제 native hold 상태/반력이 일치해야 한다.
#### ASTER-USER — 기존 제한 + 선정한 사용자 모델 확장

Code_Aster 17.4.0, 고정 소스 50ebc13c70ee9df62faf93ddcb746a3757b3042a, 기존 설정된 Linux/SIF worker 와 Windows Qt/FreeCAD 입력·결과. 현재 frozen C3D10 선형 경로를 재사용하고, TETRA10/HEXA8 사용자 다영역 ELAS 및 VMIS_ISOT_LINE small-strain, 명시 elastic geometric-nonlinearity·단계 상태 연속으로 확장한다.

**수용 경계:** Aster 계산 자체를 Windows native 라고 주장하지 않는다. 기존 optional Linux 실행 환경에서 해당 capability 를 실행하며 Research·CCX/Impact 기본 경로는 비 WSL 이다. Aster 17.4 의 source/build/SIF identity 와 worker 수용은 소프트웨어 인수이며 새로운 유료 서버·solver 도입이 아니다. Windows 한 프로세스에서 모든 Aster 조합을 실행한다는 약속은 하지 않는다.
#### ASTER-HARD — 선정한 필수 개발 목표

ASTER-USER 의 TETRA10/HEXA8 두 3D body. native DEFI_CONTACT CONTINUE 계열의 Signorini 비관입/상보성 formulation, 마찰 없음 또는 Coulomb. small sliding 과 updated large sliding 을 실제 native 설정으로 구분하고 signed gap/압력/접선력·pair 를 보존한다.

**수용 경계:** 선형 penalty 강성을 키운 것을 hard contact 로 인증하지 않는다. 고정 17.4 catalog 와 native contact DOF/출력의 조합 확인은 B1.5.L01/L05 및 B1.6.L01 의 필수 구현 단계다. 일반 웹 설명이나 다른 버전 예제는 이 runtime 의 수용 증거가 아니다.
#### ASTER-COH — 선정한 필수 개발 목표

ASTER-USER 의 HEXA8 bulk 대향 quad face 에 zero-thickness 3D_JOINT/HEXA8 + CZM_LIN_REG 한 조합을 선택한다. 입력은 RUPT_FRAG 의 SIGM_C, 단일 GC, PENA_ADHERENCE, PENA_CONTACT 와 명시 방향이다. GC 는 energy/area, SIGM_C 는 stress, 두 PENA 값은 수치 정규화/접촉 입력이며 임의 독립 초기강성·GI/GII 를 덧붙이지 않는다. 개구와 접선 slip 의 공통 법칙, 비가역 임계 κ, unload/reload 와 압축 penalty 를 구분한다. 별도 hard-contact profile 또는 LAW117 POWER/BK 와 같은 법칙이라고 표시하지 않는다.

**수용 경계:** 공식 EDF DocAster SSNP118 모형 E 는 3D_JOINT/HEXA8+CZM_LIN_REG, R7.02.11 §5.1 은 위 네 입력을 명시한다. 이 일반 원문 확인과 고정 17.4 의 실제 계산 수용은 다르다. 17.4 catalog·원 내부변수·압축·에너지 채널의 실제 입증은 B1.5.L02 에서 닫는다. 본 정의에 XFEM 용 CZM_LIN_MIX 를 혼용하지 않는다. 부분 연화에서도 native joint 의 압축지지와 독립 contact 를 중복 활성화하지 않는다. 목표 조합을 현재 지원 인증으로 승격하거나 unsupported 로 종료하지 않는다.
#### CONTACT-STAGES — 기존 일부 + 선정한 필수 확장

기존 CCX 정적 linear-contact ADD/REMOVE 는 유지한다. Aster17.4 의 두 body, 2–4 정적 단계: tied/구속 상태→명시 해제→hard contact 활성/비활성→제하. 각 단계는 native u/σ/VARI 와 변형 기하를 인계한다. 실패 단계의 accepted prefix 와 원판정은 유지한다.

**수용 경계:** 삭제된 constraint 를 그대로 두고 표시만 바꾸지 않는다. 해제 후 자동 치유/재접합 및 dynamic tie release 는 이번 유한 조합에 없다. 그 외 기존 지원 단계는 그대로 남는다.
#### CCX-TIE — 기존 평면 + 선정한 곡면/연쇄 확장

CalculiX2.22 C3D10 TRI6 face. quadratic surface projection, 내부·edge·corner, 사용자가 명시한 거리 한계, 최대 세 body 의 비순환 A→B→C chain. 상류 adjustment 가 후행 master 위치에 반영되고 원 mesh 와 effective mesh 를 구분한다.

**수용 경계:** 모호한 다중 projection·순환·거리 초과는 해당 pair 에서 막는다. 일반 임의 곡면 CAD 재메싱/다중 해 탐색을 요구하지 않으며 최근접 절점 근사로 통과시키지 않는다.
#### CCX-PERIODIC — 기존

CalculiX2.22 C3D10 탄성 정적, 양쪽 명시 node sets, DOF1–3, proper rotation 과 translation 의 정확 대응, 중복·자유도 충돌 검사. 기존 periodic constraint writer 와 원행 결과를 재사용한다.

**수용 경계:** 이미 있는 periodic helper 를 재개발하지 않는다. 회전 자유도 beam-periodic·임의 Bloch periodic 는 필수 추가가 아니다.
#### CCX-DYNAMIC — 기존

CalculiX2.22 C3D10 탄성/J2, 현재 허용 linear/Coulomb contact, global nodal U/V1–3·밀도·Rayleigh 질량/강성 감쇠, numerical damping 별도. 정적→동적과 실제 native restart WRITE/READ 는 구분한다. checkpoint 는 같은 native build/mesh/material/state identity 에만 이어 붙인다.

**수용 경계:** 현재 dynamic tie 차단과 미지원 output 제한을 그대로 보존한다. restart reader·stream·복구 engine 은 새로 만들지 않으며 native continuation 인수만 A 로 남는다.
#### IMPACT — 기존

OpenCourant/OpenRadioss 계열: source cb760c206e346eff12161a2268b134ef9d48a4ef, Windows release latest-20261011. Starter/Engine/config/animation·TH converter 의 개별 SHA 는 caelab/adapters/opencourant_runtime.py 의 고정 identity 를 그대로 사용한다. 원 upstream 3e48bf6 와 같은 commit 이라고 합치지 않는다.

**수용 경계:** 새 binary 다운로드·자동 runtime 교체는 이 종료 계획에 없다. converter source commit 이 NOT_PROVEN_BY_RELEASE 인 한계도 남긴다. 정확한 raw 채널의 생산/변환 의미를 별도로 입증한다.
#### IMPACT-INP — 기존 flat + 선정한 계층 확장

현재 flat INP 의 C3D4/C3D8/C3D8R/C3D10/COH3D8, 기존 elastic/plastic/LAW36/LAW117 material assignment 를 유지한다. PART/ASSEMBLY/INSTANCE·translation/rotation·include 와 원 file/line/occurrence 를 동일 지원 family 에 확장한다. set/surface/BC/load 의 인스턴스 의미를 보존한다.

**수용 경계:** Abaqus 의 임의 모든 keyword 번역기가 목표가 아니다. native 변환 후 실제 PROP/SOLID·material·mass·contact postflight 를 거쳐야 한다. C3D8 이라는 이름만으로 실제 native IP 를 추정하지 않는다.
#### IMPACT-RAD — 기존 native 문서 + 선정한 편집 확장

원 native Starter/Engine/include 문서를 보존하는 기존 RAD 경로. 현재 ELAST TETRA4·TYPE24·TH 지원을 유지하며 LAW36/INIEVO bulk 와 positive-thickness LAW117 계면의 제한된 material/property/set/output 편집을 추가한다. free-format 임의 rewrite 가 아니다.

**수용 경계:** 기존 A owner/source/admission/adapter 를 재사용한다. 지원하지 않는 카드는 보존/영향 표시하고 dependent edit/run 만 명시 제한한다. 원문 전체를 새 덱으로 바꿔 누락시키지 않는다.
#### IMPACT-BULK — 기존 한 조합, native 수용 잔여

LAW36 + FAIL/INIEVO: INITYPE=1, EVOTYPE=2, EVOSHAP=1, ILEN=0, FAILIP=1, 실제 변환 Isolid=24·1IP 조합. 시작 map 의 eta/rate 와 LAW36 rate 경로, raw eta 와 [-1,1] clipped eta 를 구분한다. Gf=N/mm, L=mm, volumetric density. TEMP 없는 initiation 경로에 native 온도 의존을 주장하지 않는다.

**수용 경계:** LAW36 자체 failure 와 추가 failure 중복 금지. native damage/criterion/active/deletion/에너지는 실제 채널별로 읽고 없는 고유 damage dissipation 을 전체 IE 차로 만들지 않는다. 입력·reader 존재를 mesh/시간·에너지 수용과 합치지 않는다.
#### IMPACT-INTERFACE — 기존 envelope + 필수 이력/재접촉

positive-thickness COH3D8 LAW117 POWER/BK, 체적 밀도, 명시 thickness/기저/강도·GIC/GIIC. 부분 손상 0<d<1 의 unload→compression→reopen 및 mixed mode, 별도로 완전 삭제 후 살아 있는 대향 bulk face 의 TYPE24 접촉→재개구를 지원한다.

**수용 경계:** 표본에서의 삭제를 native 모든 증분의 삭제 연동이라고 하지 않는다. 실제 native 활성/gap 정책으로 압축 이중계상을 막아야 B2.6.L03 이 닫힌다. 초기 paired-corner geometry 와 native IP opening/contact gap 은 별개다. LAW117 은 cyclic fatigue 모델이 아니다.
#### FATIGUE — 기존

기존 S–N/rainflow 와 strain-life CMB, 단축 SWT mean-stress, 동시 Cauchy stress/total small-strain tensor 의 실제 finite sampled critical-plane SWT. plane→cycle→원 위치/행/시각과 engineering/tensor shear·unit·frame 를 보존한다. 사용자 교정과 계산 적용범위가 명시되어야 한다.

**수용 경계:** 이미 있는 C 엔진을 다시 개발하지 않는다. FS/Brown–Miller/임의 대변형 피로/LAW117 의 fatigue 재명명은 필수 추가가 아니다. 수명 계산 완료와 실제 물성의 durability 승인은 구분한다.
#### DATA — 기존

기존 CSV/ASCII·테이블·시계열 import, 명시 channel/unit/calibration/zero/offset/범위, processing DAG·mask/hide/weight/fit/holdout·원행 lineage. 분석은 전체 승인 자료, UI preview 는 별도 제한이다. 가상화/페이지 조회는 원자료 크기를 줄이는 연산이 아니다.

**수용 경계:** 1000행 preview 를 전체 처리 부재로 해석하지 않는다. 허용 연산과 large-source 정책은 현재 schema/worker 그대로, 새로운 범용 ETL 프레임워크를 만들지 않는다.
#### MATERIAL — 기존

기존 J2, 명시 DP, Neo-Hooke, single-branch Maxwell 및 지원 MFront material-point. 단축/동축 finite observation, A0/L0·현재 A 또는 F/J, prescribed/mixed stress-strain control·time/initial state, 다시험 fit·독립 holdout·보존 후보/명시 채택을 유지한다.

**수용 경계:** 법칙마다 실제 지원 측도·기저·변형 수준을 확인한다. gauge/crosshead 를 같다고 취급하거나 예제값을 사용자 기본물성으로 넣지 않는다. 재료점 지원과 FE 지원은 별개다.
#### LAW-FE — 기존 실제 FE

기존 FELUPE 기반 Hex8·2×2×2 Gauss IP, 명시 DP/Neo-Hooke/single-branch Maxwell. 기존 지원 affine 및 uniaxial/free-lateral mixed boundary, point/FE state·stress·tangent 저장. FreeCAD DP→동일 frozen simulation→새 owner FE 경로의 기존 구현을 재사용한다.

**수용 경계:** FELUPE 숫자 버전은 이 ZIP 에서 import 하는 plugins/material_point/law_native.py 가 빠져 있어 독립 확정할 수 없다. runtime.py 의 FELUPE_VERSION 상수/ABI/hash 계약을 보존하고 B8.6.L01 이 해당 원문·정확 설치버전을 회수한다. 이 누락을 세 법칙 FE 부재나 재개발 사유로 바꾸지 않는다.
#### LAW-FE-THERMAL — 선정한 필수 확장

기존 FELUPE Hex8 FE 에 두 bulk region 과 thermal eigenstrain·일반 사용자 경계조건을 연결한다. Case C 는 선형탄성층+small-strain single-branch Maxwell 층의 자유/구속 이중층으로 고정한다. Tref 에서 α(T−Tref)I 를 정확히 한 번 반영하고 보존 IP state 와 실제 시간으로 이력·회복을 읽는다.

**수용 경계:** 기존 DP/Neo/Maxwell point/FE 엔진 재작성 없음. Neo-Hooke 열 대변형 등 다른 조합은 이번 필수 추가가 아니다. 계면 손상 Case C 변형은 ASTER-COH/IMPACT-INTERFACE 중 명시 solver 경로와 별도로 구분하고 어느 쪽 결과인지 보존한다.
#### MFRONT-FE — 선정한 한 FE pair

TFEL 5.0.0 + MGIS 3.0, 기존 고정 Linux image/worker. 사용자 MFront Generic interface 의 3D small-strain behavior 한 profile 을 기존 FELUPE Hex8 FE 의 integration point 재료 응답으로 사용한다. strain/stress 의 Kelvin/engineering 변환과 tangent, state commit/rollback 을 명시한다. 범위는 탄성 및 small-strain J2 형 behavior 로 확인한다.

**수용 경계:** 현재 user_mfront_worker 는 MGIS 재료점이고 FEexport=false 다. 먼저 이 한 FE pair 를 실제 구현한 뒤에만 FE 가능으로 표시한다. CalculiX/Code_Aster 카드 export, 모든 finite-strain MFront behavior, Windows native compiler 를 이미 지원한다고 하지 않는다. compile 은 명시 동작, 결과 재열기에는 compiler/solver 호출 0.
#### NUM — 기존

기존 typed real/integer/discrete/categorical 변수·단위 있는 종속식, DOE/LHS, 공동 UQ/Sobol, inverse/DE/least-squares, local RBF, Pareto·3개 이상 목적 선택. 현재 변수/분포/예산 schema 와 기존 SciPy/SALib 기반 실행을 재사용한다.

**수용 경계:** 실패 후보는 penalty/0 으로 바꾸지 않고 missing/failed/infeasible 를 보존한다. 현재 런타임 lock 의 정확 버전/seed/설계 순서가 재현 identity 이며 숫자 최신 버전을 추정하지 않는다.
#### DERIVATIVE — 기존 방법의 유한 배치

① 선형 scalar P1·고정 geometry 의 coefficient 민감도에는 기존 adjoint. ② 보존 nonlinear Material/FE 후보의 ordinary-residual 진단에는 기존 명시 FD(h,h/2/경계 one-sided). ③ transient/형상/연성의 필수 탐색은 기존 derivative-free(DE/DOE/대리모델)와 명시 평가 예산. 범주/정수에는 gradient 를 만들지 않는다.

**수용 경계:** 비선형/시간/형상/연성 네 개 범용 adjoint 를 추가하지 않는다. finite-difference 진단을 최적화기가 실제 소비하는 adjoint 로 바꾸어 부르지 않는다. 사용자가 gradient 를 요구한데 해당 profile 이 없으면 그 method 만 명시 거절하고 지원 탐색은 유지한다.
#### EVALUATION — 기존

기존 Evaluation 문서의 declared 단계, 상태 전달, 순차/Picard 반복·완화·정지 규약, nested MDO/Plan 정확 ref. 후보마다 새 상태를 만들고 NOT_CONVERGED/실패 stage 의 출력은 유효 목적값에서 제외한다.

**수용 경계:** 반복 partial checkpoint 가 미지원인 경로에 restart 를 만들지 않는다. 원 요구의 저장/재개는 정의·원결과 cold read 를 포함하되 모든 내부 iteration 에서 이어 풀겠다는 새 요구가 아니다. 기존 B5.6/B6.4 는 한 leaf 가 공동 충족한다.
#### PDE — 기존 선언한 실행 목록

Windows: 기존 SciPy ODE(1–16 state, 명시 parameter/time/IC; RK45/DOP853/Radau/BDF)와 scikit-fem 의 2D 직사각형 P1, 최대 8192 TRI3, 정상 열전도/명시 선형 scalar weak form 및 등방 small-strain plane-stress 열탄성이다. source snapshot 의 시각 선택/보간은 transient 열/구조 적분기가 아니다. 비선형·시간·벡터 공간모델은 기존 선택적 FEniCSx worker 가 실제 허용한 declared weak-form/type registry 로 구분한다. Evaluation 의 Picard/MDO 반복이 Windows P1 솔버 자체를 비선형·동적 솔버로 바꾸지는 않는다.

**수용 경계:** Windows P1 은 scikit_fem_models.VERSIONS 의 scikit-fem 12.0.2, NumPy 2.3.5, SciPy 1.17.0 을 사용한다. 이 소스 선언과 설치 성공은 별개이며 실제 receipt 로 확인한다. 선택 FEniCSx 의 고정 version tuple 도 기존 worker 계약으로 확인한다. 없는 일반 PDE·임의 script 를 지원한다고 하지 않는다. 기본 Windows 경로의 WSL 비필수와 optional FEniCSx Linux 계산을 분리한다.
#### STRESS-CONVERT — 진행 중 Sol 코드; 이 ZIP 에는 없음

같은 위치/시각의 Cauchy σ, Kirchhoff τ, PK1 P, PK2 S 를 공통 Cauchy 로 비교한다: τ/J, PFᵀ/J, FSFᵀ/J. full F/J>0·양쪽 기저·tensor component ordering 이 필수다. PK1 은 일반 비대칭 9 성분이며 sym6 로 잘라 넣지 않는다.

**수용 경계:** 단위·회전·native/derived 표시, 필요한 F/시간/행 없는 곳의 mask 를 보존한다. native_post_delivery 소유의 기존 작업을 재발주하지 않고 B3.2.L01 로 회수·통합한다.
#### STRAIN-CONVERT — 선정한 필수 비교 확장

total Green-Lagrange E를 공통 참조 측도로 고정한다. Euler-Almansi e는 E=FᵀeF로 변환하므로 F가 필수다. material Hencky H는 E=(exp(2H)−I)/2로 변환하며 E/H만의 변환에는 F가 필수가 아니다. reference configuration과 원 기준 기저·변형 후 공간 기저를 구분하고 C의 SPD를 검사한다. F가 제공되면 detF>0과 C=FᵀF 정합을 명시된 출력 정밀도 근거로 확인한다. F가 없는 경우 방향·detF 검증까지 완료했다고 표시하지 않는다.

**수용 경계:** small strain은 같은 small-strain끼리만 비교하고 큰 회전의 ε를 E로 재명명하지 않는다. elastic/plastic/integrated strain을 total로 섞지 않는다. spatial Hencky h의 새 변환은 이번 유한 확장의 필수 경로가 아니다. 수치 정합 bound는 producer의 출력 형식·정밀도에 근거해야 하며 임의 자유문구만으로 native 검증 통과를 표시하지 않는다.
#### SPATIAL — 기존 P1 + 선정한 고차 확장

기존 same_mesh 와 linear_tetra_b_to_a 를 유지한다. 추가 공간 mapping 은 TETRA10/HEXA8/HEXA20 의 명시 nodal field, isoparametric inverse mapping 와 해당 차수 shape function 으로 한정한다. 대상 point 의 유일한 포함 element·bounds·Jacobian·coverage 를 기록한다.

**수용 경계:** 원 IP/cell field 를 nodal interpolation 이라고 하지 않는다. projection 이 필요하면 원 producer 가 명시한 recovery/association 으로 별도 표시한다. 고차 midpoint 를 버리거나 nearest node 로 채우지 않는다.
#### SURFACE — 기존 선형 + 선정한 고차/현재 면적

TRI3/QUAD4 기존 측정을 유지하고 TRI6/QUAD8 의 parametric area quadrature 를 추가한다. scalar 또는 명시 tensor/vector component 의 weighted mean. reference geometry 와 current X+U geometry 를 명시 선택하고 U 단위·기저·실제 time·node identity 가 맞아야 한다.

**수용 경계:** TRI6 에는 7-point, QUAD8 에는 5×5 Gauss 를 기본 적분으로 고정하고 작은 고차 quadrature 대조로 정확도를 확인한다. 원 native IP 면적과 derived geometric area 는 구분한다. missing/degenerate/folded face 는 면적 0 으로 통과시키지 않는다.
#### MULTIBLOCK — 선정한 measurement 확장

ParaView6.2 multiblock 의 실제 leaf selector/path+원 node/element ID+array association·component·time. 명시 선택한 leaf 들의 point/path/surface/gauge 와 집계 none/sum/area-weighted mean. 두 점은 각자의 leaf/path 를 보존한다.

**수용 경계:** 같은 숫자 ID 라도 다른 leaf 면 다른 객체다. ghost/중복 cell 을 사전 검증하며 좌표가 같다는 이유로 실제 다른 물체를 합치지 않는다. 일부 leaf 실패의 coverage/mask 와 각 원행 복귀를 보존한다.
#### TR-U — 선정한 vector producer/receiver

Producer=보존 CCX2.22 C3D10 displacement nodal U, Receiver=다른 C3D10 경계의 prescribed displacement. 명시 actual time, reference surface 의 quadratic H mapping, mm 단위·proper rotation 과 선택 DOF. 적용될 receiver BC 만 새 입력에 쓴다.

**수용 경계:** 상수·affine displacement 와 rigid rotation/translation 재현, source 밖 target mask/거절. 이 port 에 힘/에너지 보존을 주장하지 않는다. field→BC 가 실제 solver 결과와 저장에 연결되어야 한다.
#### TR-S — 선정한 tensor/state producer/receiver

Producer=보존 CCX2.22 C3D10 의 실제 native IP Cauchy6 stress, Receiver=동일 mesh/동일 IP ordering 의 CCX2.22 탄성 초기응력. 단위·정확 tensor 기저 회전·reference state·시간을 명시한다. 초기 변위/상태 일관성은 INIT-THERMAL 과 공동 검사한다.

**수용 경계:** 다른 mesh tensor smoothing, plastic/viscoelastic restart, C3D10 과 Aster 의 다른 integration rule 을 같은 IP 로 간주하는 것은 지원목록에 없다. 상태정보가 더 필요한 법칙은 native restart 를 사용해야 한다.
#### TR-F — 선정한 보존 전달 producer/receiver

Producer=실제 native 한 interface side 의 nodal force 와 좌표, Receiver=다른 C3D10 boundary 의 nodal force load. source displacement 를 target DOF 에서 재현하는 quadratic H 를 만든 뒤 f_target=Hᵀ f_source 로 전송한다. F 와 지정 기준점 M 및 가상일을 검사한다.

**수용 경계:** H 가 partition of unity 와 affine coordinate reproduction 을 만족해야 힘·모멘트 보존을 주장한다. all-contact resultant 를 pair nodal field 로 풀어 만들거나 traction×임의 면적으로 합성하지 않는다. 양쪽 side 를 동시에 더하지 않는다.
#### TR-T3D — 선정한 Case C 전달

Producer=기존 Windows scalar P1 T(x,y,t), Receiver=그 평면의 z-extrusion 으로 정의한 3D bilayer mesh 의 nodal T/Tref. 명시적으로 z 방향 불변 온도라는 모델링 가정을 사용한다. 공간 containment 와 실제 time interpolation 구간/coverage 를 보존한다. receiver 는 LAW-FE-THERMAL 또는 ASTER-COH 의 실제 구조/계면 모델이다.

**수용 경계:** 일반 3D 열장의 z 변화를 임의로 0 으로 놓지 않는다. 전달 T 는 상태량이며 보존 heat flux 라고 하지 않는다. 구간 밖 외삽·중복 Tref 차감·unconverged P1 결과 소비는 거절한다.
#### RESEARCH — 기존

Study 단독 생성·판단·evidence/decision/다음 시험, exact knowledge source 와 원문 위치·결과 ref, 원자료 없는 portable 재열기. 문헌만으로도 Report 를 만든다. 원문 미확인·변경·누락은 판단 성공으로 바꾸지 않는다.

**수용 경계:** Expert/AI/OpenScience 구독 없이 Study·문헌·보존 결과를 읽고 편집·저장할 수 있어야 한다. 새 문헌 DB/권한 체계를 만들지 않는다.
#### EXPERT — 기존

기존 세 역할 초기 조사→상호질문/답변→지도→보고서, current provider 와 실제 author/source 기록, 제한·중단·재개·불완전 응답. 이미 보존한 실제 round 를 회수하여 사용하고, 수정된 연결이 요구하는 최소 live round 만 기존 승인 비용 범위에서 수행한다.

**수용 경계:** 새 유료 API/자동 provider fallback 은 0. provider 가 없으면 draft 와 보존 자료는 사용 가능, 새로운 실제 답변이 생성됐다고 하지 않는다. 제품 inference 와 Pro 개발 작업은 다른 수명이다.
#### UNCERTAINTY — 기존 엔진 소비 + Sol 연결 잔여

기존 표준/확장 불확실성(k), 단위, 부분 공분산·PSD, calibration_problem/processing_problem, Jacobian JΣJᵀ를 사용한다. 실제 같은 관측량 r=B−A 의 Σr=ΣB+ΣA−ΣBA−ΣAB 를 명시된 공분산으로 계산한다. 비선형 교정/측도/게이지 chain 은 현재 관측점에서의 1차 전파로 고정한다.

**수용 경계:** 비선형 Jacobian 은 analytic 또는 기존 명시 FD 를 쓰고 작은 h/절반 h 기준을 확인한다. 전역 nonlinear 분포/정규성/신뢰구간은 자동 주장하지 않는다. 알려지지 않은 교차공분산을 0 으로 가정하지 않으며 사용자가 독립을 선언한 경우만 기록한다. dynamic_reprocess_gui 작업을 중복 발주하지 않는다.
#### IDENTIFICATION — 기존

immutable 선택 후보의 ordinary-residual Jacobian 을 기존 experiment_final_diagnosis 로 명시 재평가한다. 최대 64 자유계수/32768 residual, 상대차분간격 1e−8…1e−2, h/2·방향 일관성, 기존 국소 SVD rank/rank-deficiency·fixed/unidentified 진단. 원 optimizer 가 robust loss/DE 여도 새 진단은 일반 잔차 기반임을 구분한다.

**수용 경계:** 통계적 profile likelihood 나 전역 유일성 판정을 요구한 것으로 원 명세를 확대하지 않는다. 지원된 국소 진단·관측·bounds·예산과 그 한계를 Study 의 다음 시험 판별 목적에 보존하면 원 FN-05-02 를 충족한다. 작은 residual 만으로 식별 성공을 말하지 않는다.
#### ACQUISITION — 선정한 공통 소프트웨어

기존 Data/JobManager/owner 위에 reusable channel/unit/calibration/sample-rate/duration/clock setup, sequence·timestamp·raw sample·source mode, connect/requested/running/stop_requested/stopped/failed/disconnected 상태와 receipt 를 연결한다. 장비 없는 인수는 명시 RECORDED_REPLAY mode 의 실제 CSV/기록 파일을 사용한다.

**수용 경계:** 같은 sequence/같은 bytes 재전달은 중복 제거, 같은 sequence/다른 bytes 는 conflict. 누락/overflow/clock reset 은 segment·gap, 원 순서·표본 보존. 파일 끝·Job 취소는 물리 stop ack 가 아니다. finite memory/backpressure·stop 요청 중 늦은 sample·쓰기 실패를 포함한다.
#### ACQUISITION-DEVICE — 외부조건 한 건

허가받은 장비 한 모델·firmware·protocol/driver 버전·주소·channel map·교정·허용 sampling·물리 stop 규약. 이 정보는 현재 미제공이다. ACQUISITION 의 adapter contract 에 실제 binding 한 개를 연결한다.

**수용 경계:** 장비명/SCPI/serial/VISA/TCP 종류를 임의로 정하지 않는다. 장비 binding 코드와 물리 취득/stop 인수는 E B7.6.L02 에 남긴다. 공통 sample/sequence/UI 개발은 그 전에 별도 D 로 끝낸다.
#### REMOTE — 기존 세 포트 + live 인수

기존 외부 file batch exchange 와 OpenSSH ssh/scp, Linux Slurm(sbatch/squeue/sacct/scancel), OpenPBS(qsub/qstat/qdel) adapter. 제출 token/job ID·command receipt, query/cancel/collect/서버 종료 상태·파일 해시를 유지한다. 자신의 job 만 제어한다.

**수용 경계:** scheduler 실제 버전·queue/account·host path/runtime 는 각 실제 host input 이다. 없는 host 를 지어내지 않는다. 포트별 deterministic transport 인수 A 와 실제 SSH/Slurm/OpenPBS 인수 E3 을 분리한다. 모의 응답·파일 복사를 live 성공으로 계산하지 않는다.
#### DOCS — 기존 owner 목록 고정

Research9종: Data, Material, Numerical, PDE, Simulation, Evaluation, Study, Expert, Report. native2종: FreeCAD Pre FCStd/project, ParaView Post project. Runner 는 새 문서 owner 가 아니라 기존 Job/result 실행·조회 창이다. 보존 결과/Plan/knowledge/raw/source 와 선택/dirty/receipt 를 각 owner 계약대로 유지한다.

**수용 경계:** portable_project.SUPPORTED 9종 및 portable_project_native 의 Pre/Post 를 구분한다. ACKNOWLEDGED 초안은 저장 revision 과 같지 않다. 원 store 없는 cold reopen/read 는 계산 0, 다시 계산은 명시 새 run 과 환경확인 후에만 한다.
#### COMMANDS — 기존 공개 명령 동등성

공통 inspect/discover/정확 doc 열기, draft 편집·check/freeze/preview/apply/reset/undo/redo, 저장/관련저장/복구, 실행/조회/취소, 결과 선택·export·exact ref return, portable·graph·external batch 의 현재 등록 operation. 아래 부록의 실제 operation 문자열 목록을 기준으로 GUI/CLI/Python/MCP 가 동일 Core/owner 를 소비한다.

**수용 경계:** 호스트 capability 에 없는 명령은 그 진입점에서 unsupported 를 그대로 반환한다. native 내부의 임의 모든 메뉴를 MCP 로 새로 구현하지 않는다. 지원 등록된 공통 명령의 기능이 빠지면 숨기지 말고 같은 leaf 의 결함으로 고친다.


## 4. 44 부모의 현재 판정과 닫을 작업

`보존`은 그 부모의 기존 확인 범위를 재개발하지 않는다는 의미다. 전체 제품 인수 통과가 아니다. 부모의 잔여는 아래 ID 들을 모두 닫고 연결된 FN/원 acceptance 를 만족할 때 종료한다. 부록의 FN 표가 기존 원문 종료조건을 그대로 보존한다.

| 부모 / 원 이름 | 현재 판정·유지할 구현 | 남은 고유 leaf | 원 FN | 기존 SPEC |
|---|---|---|---|---|
| B1.1 M4 편집 모델 | M4 독립 FE 모델·occurrence 참조와 기본 CAD/메시/기존 FEM 왕복 구현·실행 기록을 보존. 새 코드 leaf 0. 최종 구조 장면에서 회귀만 확인. | 보존·구조 통합장면 회귀만 | FN-10-01, FN-10-02, FN-11-01, FN-13-01, FN-13-02 | PREFE-001(M/E/C/R/N/S), CONTACT-001, CAD-NUMERICAL-001 |
| B1.2 기구의 남은 일반 관계 | motion_relation 의 다변수·차원/DAG 까지 이미 존재. 일반 관계 엔진 신규 개발로 재분류하지 않고 native 사용 인수만. | L01(A) | FN-11-01, FN-11-02 | PREFE-001(M/E/C/R/N/S), CONTACT-001, CAD-NUMERICAL-001 |
| B1.3 셸·빔 잔여 | 곡면·영역 S8 및 RECT B32R raw/section-force 경로 존재. native 일반화 회전·완전 구속반력/모멘트·IP 원좌표 공백은 별도 D. | L01(A), L02(D) | FN-12-02 | PREFE-001(M/E/C/R/N/S), CONTACT-001, CAD-NUMERICAL-001 |
| B1.4 복합재·초기장·연결요소·체결 | 기본 재료/하중·구속·밀도/동적 IC 는 존재. 적층/초기 tensor·열/연결요소/pretension 네 사용자 기능이 D. | L01(D), L02(D), L03(D), L04(D) | FN-12-01, FN-12-02 | PREFE-001(M/E/C/R/N/S), CONTACT-001, CAD-NUMERICAL-001 |
| B1.5 접촉/구속 C1–C6 | linear contact·평면 tie·일부 단계·periodic 존재. hard/implicit cohesive/곡면 chain/sliding/tie release 의 선정 조합만 추가. | L01(D), L02(D), L03(D), L04(D), L05(D), L06(A) | FN-14-01, FN-14-03, FN-17-01 | PREFE-001(M/E/C/R/N/S), CONTACT-001, CAD-NUMERICAL-001 |
| B1.6 접촉 응답·비선형 조합 | CCX J2/NLGEOM 와 기존 접촉 출력 존재. 새 접촉 profile 의 정확 출력과 사용자 Aster 비선형은 D; 기존 NS1 은 A. | L01(D), L02(A), L03(D) | FN-14-02, FN-15-01, FN-15-02 | PREFE-001(M/E/C/R/N/S), CONTACT-001, CAD-NUMERICAL-001 |
| B2.1 NS2 초기 상태·시간 해석 | 초기 U/V·밀도·감쇠·시간 설정/실행 코드 존재. 지원 dynamic profile 의 현재 사용자 인수만. | L01(A) | FN-12-02, FN-15-01, FN-15-02 | PREFE-001(NS2/N3), IMPACT-001 |
| B2.2 N3 정적→동적 | 정적→동적 본코드 존재. 상태 의미/실제 초기조건/저장 사용 인수만. | L01(A) | | PREFE-001(NS2/N3), IMPACT-001 |
| B2.3 시간별 결과 | stream/retained frame/원실패 복구 및 Impact 전용 readback 존재. 새로운 stream/store 엔진 없음. | L01(A) | FN-15-02, FN-16-02, FN-25-01, FN-25-02 | PREFE-001(NS2/N3), IMPACT-001 |
| B2.4 실제 restart | restart source/checkpoint/WRITE/READ 본코드 존재. Windows 실제 continuation 수용은 별도 A. | L01(A) | FN-25-02 | PREFE-001(NS2/N3), IMPACT-001 |
| B2.5 일반 충격 입력 | flat 일반 INP 와 제한 계층/native RAD 경로 존재. 기존 flat family·law 를 계층/native 명시 편집에 연결하는 두 D. | L01(D), L02(D) | FN-16-01 | PREFE-001(NS2/N3), IMPACT-001 |
| B2.6 충격 결과·손상·피로 | LAW36/INIEVO·LAW117·TH pair·sample impulse·εN/SWT/CP 엔진 존재. 부분 손상 loop 와 완전삭제 재접촉만 새 D, 나머지 한정 인수. | L01(A), L02(D), L03(D), L04(A), L05(A) | FN-16-02, FN-17-01, FN-17-02 | PREFE-001(NS2/N3), IMPACT-001 |
| B3.1 선택과 닫기 | PV 주창/작은 Qt 선택 설정·native 분할이 이미 게시됨. 새 GUI 설계가 아니라 실제 사용 인수와 별도 managed close/SDK 인수. | L01(A), L02(A) | FN-27-01, FN-27-02 | POST-COMPARE-001, POST-NUMERICAL-001, DESKTOP-001/002 |
| B3.2 비교 변환의 잔여 | stress conversion/B−A connection 은 `e76cde6`에서 통합되어 L01(A) 사용자 인수만 남음. strain 의미와 고차 mapping 은 D. | L01(A), L02(D), L03(D) | FN-28-01, FN-28-02 | POST-COMPARE-001, POST-NUMERICAL-001, DESKTOP-001/002 |
| B3.3 측정의 재사용 | 점/경로/시간/선형면 평균/두점 이력 존재. 고차 face, multiblock, current area 의 세 추가만. | L01(D), L02(D), L03(D) | FN-14-02, FN-27-01 | POST-COMPARE-001, POST-NUMERICAL-001, DESKTOP-001/002 |
| B3.4 복구·보고 반환 | 원결과교체·repair/branch·origin return 와 보존 코드 존재. 현재 source 에서 정확 cold 왕복 인수. | L01(A) | FN-14-03, FN-28-03 | POST-COMPARE-001, POST-NUMERICAL-001, DESKTOP-001/002 |
| B4.1 처리 recipe | processing DAG/원행/mask/weight/큰파일 처리 존재. preview 제한을 처리 부재로 오판하지 않음. | L01(A) | FN-04-01, FN-04-02, FN-04-03 | RESEARCH-003(FN03/04/06/07/09), EXPERIMENT-001, NUMERICAL-002 |
| B4.2 유한변형 측도 | finite observation 및 같은 측도 prediction/fit/holdout 존재. 사용자 전체 흐름 인수. | L01(A) | FN-03-01, FN-03-02, FN-06-01 | RESEARCH-003(FN03/04/06/07/09), EXPERIMENT-001, NUMERICAL-002 |
| B4.3 실제 시험 제어 | mixed control/multitrial/횡방향 자유 조건 존재. 제어 의미와 상태보존 인수. | L01(A) | FN-06-01, FN-06-02, FN-07-01 | RESEARCH-003(FN03/04/06/07/09), EXPERIMENT-001, NUMERICAL-002 |
| B4.4 후보 상세 보존 | 보존 후보 상세·명시 새 평가·채택 존재. 새 store/후보 엔진 없음. | L01(A) | FN-04-03, FN-07-02, FN-07-03 | RESEARCH-003(FN03/04/06/07/09), EXPERIMENT-001, NUMERICAL-002 |
| B4.5 재료군·FE 전달 | DP/Neo/Maxwell Hex8 FE 존재. Case A 인수와 Case C 다영역 열·회복 사용자 연결만 잔여. MFront FE 는 B6.1 에서 1회 계수. | L01(A), L02(D) | FN-08-02, FN-09-01, FN-09-02 | RESEARCH-003(FN03/04/06/07/09), EXPERIMENT-001, NUMERICAL-002 |
| B4.6 기존 6행 완료 대조 | 옛 6 행은 독립 신규 task 가 아니다. B4.1–5 및 B8.2 의 행 보존/mask/채택/부분저장 증거로 교차 닫음. | B4.1–5/B8.2 증거 재사용; 독립 leaf0 | FN-03-01, FN-04-01, FN-04-03, FN-07-01, FN-07-03, FN-09-02 | RESEARCH-003(FN03/04/06/07/09), EXPERIMENT-001, NUMERICAL-002 |
| B5.1 변수와 DOE | typed DOE·종속값 engine 존재. 기존 native/FE 평가 소비와 인수만. | L01(A) | FN-20-01, FN-20-03 | NUMERICAL-001/002, CAD-NUMERICAL-001, RESEARCH-003 |
| B5.2 민감도·UQ | 공동 UQ/상관/PSD/Sobol 및 최신 Windows 수용 기록 존재. 새 엔진·독립 잔여 0; 변경 영향 회귀만. | 보존; 변경 영향 회귀만 | FN-20-02, FN-22-01, FN-22-02 | NUMERICAL-001/002, CAD-NUMERICAL-001, RESEARCH-003 |
| B5.3 일반 역해석 | general inverse/feasibility·실제 evaluator 존재. 선택한 Case A/B 목적/관측 연결 인수. | L01(A) | FN-05-02, FN-21-01 | NUMERICAL-001/002, CAD-NUMERICAL-001, RESEARCH-003 |
| B5.4 gradient/adjoint | 선형 P1 adjoint·명시 FD·derivative-free 존재. 네 일반 adjoint 신규개발 0. 방법별 표기/소비/오류 인수. | L01(A) | FN-21-02 | NUMERICAL-001/002, CAD-NUMERICAL-001, RESEARCH-003 |
| B5.5 국소 대리모델 | localRBF 와 저장/예측·범위 밖 구분 및 최신 인수 기록 존재. 새 잔여 0. | 보존; 변경 영향 회귀만 | FN-23-01 | NUMERICAL-001/002, CAD-NUMERICAL-001, RESEARCH-003 |
| B5.6 과거 학습 모델·다목적·MDO | retained surrogate·다목적/Pareto axes·MDO/Picard 존재. B6.4 와 같은 사용자 인수를 1회 계수. | L01(A) | FN-23-02, FN-24-01, FN-24-02 | NUMERICAL-001/002, CAD-NUMERICAL-001, RESEARCH-003 |
| B6.1 구성식 검사·interface | 세 법칙 Hex8 FE 및 state/tangent 검사 존재. user MFront FE=false 의 한 실제 FE pair 만 새 D. | L01(D), L02(A) | FN-08-01, FN-08-02, FN-09-01, FN-09-02 | RESEARCH-003(FN08/18/19), NUMERICAL-002 |
| B6.2 독립 식 연구 | Windows ODE/P1 및 optional FEniCSx 코드 존재. 원 선언 equation 의 독립 편집/실행/재개 인수. | L01(A) | FN-18-01, FN-18-02 | RESEARCH-003(FN08/18/19), NUMERICAL-002 |
| B6.3 실제 mapping | 서로 다른 mesh/time P1 온도→열탄성은 이미 존재. U→BC, σ→초기 state, 보존 nodal-force, Case C 3D 온도 receiver 네 finite D. | L01(D), L02(D), L03(D), L04(D) | FN-19-02 | RESEARCH-003(FN08/18/19), NUMERICAL-002 |
| B6.4 반복 연성·재사용 | Evaluation/Picard/MDO 존재. B5.6.L01 에서 공동 인수하며 scheduler/반복엔진을 중복 개발하지 않음. | B5.6.L01 공동 소비; 중복 0 | FN-19-01, FN-19-03, FN-24-02 | RESEARCH-003(FN08/18/19), NUMERICAL-002 |
| B7.1 문헌과 판단 | exact 문헌/Study/지식자료/portable 연결 존재. 실제 원자료·판단·cold·broken repair 인수. | L01(A) | FN-29-01, FN-29-02, FN-29-03 | EXPERIMENT-001, EXPERT-001/002, DESKTOP-002 |
| B7.2 실제 Expert 왕복 | 세 역할 실제 초기 조사/상호질문/지도/보고 실행 기록 존재. 제한/실패/재개 의미의 제품 인수. | L01(A) | FN-30-01, FN-30-02 | EXPERIMENT-001, EXPERT-001/002, DESKTOP-002 |
| B7.3 불확실성·계측 대응 | JΣJᵀ·부분공분산/PSD·Plan/Study 엔진 존재. 실제 B−A 관측 chain 연결만 Sol 의 D. | L01(D) | FN-05-01 | EXPERIMENT-001, EXPERT-001/002, DESKTOP-002 |
| B7.4 식별성과 다음 시험 | robust/DE 후보의 명시 ordinary-residual FD final diagnosis 까지 존재. 새 식별엔진이 아니라 진단→다음시험 인수. | L01(A) | FN-05-02 | EXPERIMENT-001, EXPERT-001/002, DESKTOP-002 |
| B7.5 3D 보고 | native scene capture/정확선택·Report PDF/MD·원자료 복귀 존재. B3.4 와 의미를 공유하되 Report 편집/출력 사용자 인수. | L01(A) | FN-32-01 | EXPERIMENT-001, EXPERT-001/002, DESKTOP-002 |
| B7.6 실장비 | 파일 import·교정·수집 설정 일부 존재. 공통 sample/sequence/error/stop receipt 소프트웨어 D1, 특정 실제 장비 binding/물리수용 E1. | L01(D), L02(E) | FN-35-01 | EXPERIMENT-001, EXPERT-001/002, DESKTOP-002 |
| B8.1 정확한 열기·최근 문서 | 독립 apps/file/recent/exact owner open 존재. 전체 지원 11종 창/문서 사용자 인수. | L01(A) | FN-01-01, FN-33-01 | DESKTOP-001/002, NUMERICAL-002(외부교환) |
| B8.2 복수 owner 편집·저장 | 복수 owner 편집/관련저장/partial receipt/실패재시도 존재. 기존 보호를 재개발하지 않고 cold 사용 인수. | L01(A) | FN-02-01, FN-02-02, FN-02-03, FN-07-01 | DESKTOP-001/002, NUMERICAL-002(외부교환) |
| B8.3 이동용 사본 | 이동사본 9 research+Pre/Post·retained inputs/실행/복구 존재. 원 store 없는 actual cold/재편집 인수. | L01(A) | FN-01-02 | DESKTOP-001/002, NUMERICAL-002(외부교환) |
| B8.4외부/원격 실행 | SSH/Slurm/PBS/file batch 코드 존재. 포트 contract 수용 A1, 실제 세 host 별 E3. 모의 성공을 live 로 합치지 않음. | L01(A), L02(E), L03(E), L04(E) | FN-25-01, FN-26-01, FN-26-02 | DESKTOP-001/002, NUMERICAL-002(외부교환) |
| B8.5 선택적 연결 보기 | graph drag/list/relation add·repair·unlink 존재. 선택/대상/저장 실제 UI 인수. | L01(A) | FN-31-01 | DESKTOP-001/002, NUMERICAL-002(외부교환) |
| B8.6 설치·동등 명령 | ZIP 고정 upstream 준비·native 발견선택 게시. 새 PC/지원명령/전체실사용의 3 인수; SDK 의 전체개발 선행조건화 금지. | L01(A), L02(A), L03(A) | FN-33-01, FN-33-02, FN-34-01 | DESKTOP-001/002, NUMERICAL-002(외부교환) |

### 영역별 중복 없는 개수

| 영역 | D 개발 | A 구현 있음·인수 | E 외부조건 | S 미결 | 합계 |
|---|---:|---:|---:|---:|---:|
| B1 | 12 | 4 | 0 | 0 | 16 |
| B2 | 4 | 7 | 0 | 0 | 11 |
| B3 | 5 | 4 | 0 | 0 | 9 |
| B4 | 1 | 5 | 0 | 0 | 6 |
| B5 | 0 | 4 | 0 | 0 | 4 |
| B6 | 5 | 2 | 0 | 0 | 7 |
| B7 | 2 | 4 | 1 | 0 | 7 |
| B8 | 0 | 8 | 3 | 0 | 11 |
| **합계** | **29** | **38** | **4** | **0** | **71** |


## 5. Leaf 별 유한한 인도 명세

다음 기록은 한 기능을 사용해서 끝내는 단위다. 파일 수로 분할하지 않는다. 한 팀 안에서도 각 파일의 실제 쓰기 담당자는 한 명으로 고정한다. `[신규]`는 이번에 제안한 파일이며 현재 ZIP 에 있다고 주장하지 않는다. 기존 공통 파일을 참조한 경우 실제 병합은 §6 의 Codex 소유 규칙을 따른다.

**모든 leaf 의 공통 오류/보존 계약:** 불완전 draft 저장 허용, 실행 전에 단위·필수 입력·정확 source/owner·지원 profile 확인, 실패에서 원입력·원결과·마지막 성공값을 보존, 취소 가능 단계와 native 실행중 중단 불가를 구분, 미확인 응답은 같은 요청 조회, 재실행은 명시 새 run, 저장 후 새 프로세스에서 같은 선택/값/원판정 읽기. 새 code/GUI 가 이 계약의 일부를 우회하면 해당 leaf 는 닫히지 않는다.

수치 기준은 기존 더 엄격한 acceptance 를 우선한다. 새 leaf 에 적힌 오차는 실행 전 고정한 매끈한 소형 문제/명시 관측 위치에 적용한다. 특이점의 peak stress 를 수렴값으로 검사하거나, 실패 뒤 tolerance·source·단위를 바꿔 통과시키지 않는다. 정확한 값은 analytic/patch test 또는 고정 native 원출력에서 얻고, 합성 데이터의 역할은 명시한다.

### B1.2.L01 — 다변수 기구·중첩 occurrence 의 마지막 native 인수

**분류 A · 단독 책임 T1(CAD·조립·구조요소) · 상대 작업량 2/3**
원 연결: FN-11-01, FN-11-02; SPEC-PREFE-001(M/E/C/R/N/S), CONTACT-001, CAD-NUMERICAL-001.

**현재 구현 / 실제 잔여:** 비율식만 있는 상태가 아니다. motion_relation 의 차원 검사·DAG·다변수 식, Revolute/Slider/Cylindrical 연결과 전용 검사가 있다. 오래된 M1 첫 인도 표의 미구현 판정을 사용하지 않는다.

**고정 지원 profile:** W, PRE, MOTION

**사용자 입력 → 조작 → 출력·저장재개:** 두 단계 조립에서 같은 원부품의 두 occurrence 와 회전·이동 구동을 선택 → 종속식/한계 편집 → native 프레임·경로 선택 → 설계 자세 복원 → 저장·새 FreeCAD 에서 동일 선택과 식 재개. 순환·중복 DOF·범위 내 극점·한계 미증명은 해당 식으로 돌아간다.

**수정 파일·서비스 / 재사용 경로:** apps/desktop_pre/motion_relation.py; apps/desktop_pre/motion_formula.py; apps/desktop_pre/motion.py; apps/desktop_pre/motion_relation_editor.py; tests/test_pre_motion_general_relations.py

**의존:** 없음; B1.1 의 완료된 M4 재사용

**최소 확인 / 실패·취소 반례:** 서로 다른 두 자유도와 두 단계 종속식 한 기구, 반복 occurrence 한 개만 구동, 순환/단위 오류 한 개씩. 실제 시각별 좌표와 설계 복원 확인. 기존 단위검사 재실행은 변경한 파일만.

**종료조건:** 입력·실제 자세/시각·Undo·정지/복원·cold reopen 이 일치. 구현 존재와 OS 조작 인수를 구별한 기록이 게시되면 닫음.


### B1.3.L01 — 곡면·영역별 S8 와 B32R 원출력의 지원 내 왕복

**분류 A · 단독 책임 T1(CAD·조립·구조요소) · 상대 작업량 2/3**
원 연결: FN-12-02; SPEC-PREFE-001(M/E/C/R/N/S), CONTACT-001, CAD-NUMERICAL-001.

**현재 구현 / 실제 잔여:** curved S8 기하와 영역별 두께/offset/압력, B32R 두 출력 모드·.12d/FRD/DAT reader 가 있다. 50IP COORD 일치 검사에서 native 좌표 문제를 감지하는 guard 도 있다.

**고정 지원 profile:** W, PRE, CCX-SHELL, CCX-BEAM

**사용자 입력 → 조작 → 출력·저장재개:** 곡면/두 영역 셸과 직선 RECT 빔을 각각 편집 → 명시 출력 모드 선택 → 실행 → 셸 상·하면/빔 50IP S·E·COORD 와 원줄 선택 → 같은 모델 저장·재열기. 무하중 전체, 부호·coverage, 재번호 모호성은 계속 차단.

**수정 파일·서비스 / 재사용 경로:** caelab/shell_model.py; caelab/shell_regions.py; caelab/beam_output.py; caelab/beam_raw_results.py; apps/desktop_pre/shell_region_native.py; caelab/adapters/shell_results.py

**의존:** B1.3.L02 가 필요한 native COORD 결함 발견 시 그 행으로 귀속; 일반 S8 사용은 대기하지 않음

**최소 확인 / 실패·취소 반례:** 영역별 0 압력/전체 무하중 반례; 곡면과 평면 두께/법선; 빔 section_forces 와 raw_stress 가 다른 명시 실행임을 확인. 좌표 오류는 계산 좌표로 채우지 않고 원 실패로 남김.

**종료조건:** 이미 지원한 셸·빔 편집/선택/보존은 닫되, native 일반화 회전/완전 반력 및 출력 결함은 L02 완료 전까지 완료로 합치지 않음.


### B1.3.L02 — B32R native 일반화 회전·완전 지지반력·50IP 관측 완결

**분류 D · 단독 책임 T1(CAD·조립·구조요소) · 상대 작업량 3/3**
원 연결: FN-12-02; SPEC-PREFE-001(M/E/C/R/N/S), CONTACT-001, CAD-NUMERICAL-001.

**현재 구현 / 실제 잔여:** beam_raw_results.UNAVAILABLE 과 beam_support_response 가 명시하는 실제 공백. section rigid-fit, FRD RF 합, 복원 응력 적분은 이미 있지만 요구한 native 양이 아니다.

**고정 지원 profile:** PRE, CCX-BEAM-OBS

**사용자 입력 → 조작 → 출력·저장재개:** 직선 B32R RECT 의 단면축·힘/모멘트·병진/회전 구속·지지집합 편집 → 실제로 생성된 mean-rotation MPC/knot 의 일반화 좌표와 공액 반력, 모든 선택 지지집합의 구속 기여 합력·기준점 모멘트, raw IP S/E/COORD 와 기타 명시 derived 회전을 구분해 읽는다. 원 절점마다 독립 회전 DOF 가 있다고 가정하지 않으며, 관측을 위해 knot 나 구속을 추가하지 않는다. 실제 출력 위치·변수 map 확정이 이 D 의 첫 단계다. 저장·재열기에서 대응이 없으면 채널을 거절한다.

**수정 파일·서비스 / 재사용 경로:** caelab/beam_raw_results.py; caelab/beam_support_response.py; caelab/beam_output.py; caelab/adapters/shell_results.py; [신규] caelab/adapters/beam_native_observations.py; 기존 CCX2.22 출력부의 명시 관측 패치(배포 원문은 패킷 밖)

**의존:** B1.3.L01 의 원문서/출력 모드 계약; 배포 B8.6.L01 은 이 관측 build 만 선택적으로 추가

**최소 확인 / 실패·취소 반례:** 축력·두 굽힘·비틀림을 가진 작은 한 빔과 지지부에도 외력이 있는 반례. native 구속 방정식/잔차와 일반화 반력의 일-공액 대응 확인, 전역 힘/모멘트 균형 1e-6 상대 기준. 출력 좌표는 printed precision bound 로 검증. 원 물리 계산 변경 금지.

**종료조건:** 기존 build 가 내보내지 못하면 2.22 기반 출력 전용 명시 build 를 별도 identity 로 제공해야 함. 자동 교체·대리값 승격 없이 원 DOF/MPC/관측 증거가 실제 cold reader 에 있으면 종료. 관측 채널을 계속 UNKNOWN 으로 두는 것은 이 행 종료가 아님.


### B1.4.L01 — E3 적층 셸의 층별 입력·출력

**분류 D · 단독 책임 T1(CAD·조립·구조요소) · 상대 작업량 3/3**
원 연결: FN-12-01, FN-12-02; SPEC-PREFE-001(M/E/C/R/N/S), CONTACT-001, CAD-NUMERICAL-001.

**현재 구현 / 실제 잔여:** 현재 S8 균질/영역별 표현은 재사용한다. E3 의 층별 입력/층 출력은 private 작성 중이며 인수 완료가 아니다. UI 층 순서는 top-to-bottom, native 층 순서는 역순이고 각 층 8IP 다. GLOBAL S/E 를 우선 출력하고 그 route 에 COORD 를 요구하지 않는다. 4층 이상 LOCAL/COORD 는 source buffer 위험이 있어 선택 출력 경로를 확인한다. 기존 S8 27IP/RF 를 적층 출력에 재사용하지 않는다. FRD 회복값은 native integration-point 원값과 구분해 보존한다.

**고정 지원 profile:** PRE, CCX-LAMINATE

**사용자 입력 → 조작 → 출력·저장재개:** 셸 영역에 층별 선형 직교이방 재료·두께·각도·순서 입력 → 합두께/축 미리보기 → 층 삭제·재정렬 Undo → 실행 → 층/IP/상하 위치별 응력·변형 선택 → 같은 적층 정의와 원값 재열기. 균질 평균재료로 대체하지 않음.

**수정 파일·서비스 / 재사용 경로:** [신규] caelab/shell_laminate.py; [신규] caelab/adapters/shell_laminate_deck.py; [신규] caelab/adapters/shell_laminate_results.py; [신규] apps/desktop_pre/shell_laminate_panel.py; 기존 shell_freeze/dispatcher 는 root hunk

**의존:** 기존 E1/재료 참조 계약만; B1.3.L02 불필요

**최소 확인 / 실패·취소 반례:** 2층 비대칭 및 3층 대칭 laminate 두 개. 적층판 A/B/D 와 단순 막·굽힘 기준을 입력 전 고정, 작은 두 mesh 에서 변위/층응력 오차 2% 이내로 접근. 순서/각도 변경과 누락 재료 반례.

**종료조건:** S8R COMPOSITE 라는 실제 별도 요소/출력 profile 로 층 계보와 결과가 이어지고, invalid draft/cold reopen 포함 시 종료.


### B1.4.L02 — E4 온도·초기 응력/변형 상태의 native 편집

**분류 D · 단독 책임 T1(CAD·조립·구조요소) · 상대 작업량 3/3**
원 연결: FN-12-01, FN-12-02; SPEC-PREFE-001(M/E/C/R/N/S), CONTACT-001, CAD-NUMERICAL-001.

**현재 구현 / 실제 잔여:** 기존 압력·변위·총힘·동적 U/V 는 그대로 둔다. 초기 tensor/온도 장을 사용자 영역과 상태 의미에 연결하는 것이 잔여다.

**고정 지원 profile:** PRE, INIT-THERMAL

**사용자 입력 → 조작 → 출력·저장재개:** 영역과 시각에 T/Tref, 초기 응력, 호환되는 초기 변형률·변위 상태를 명시 → 단위/기저/구속 일치 검사 → 초기 상태와 뒤 하중 계산 → 원 상태·첫 평형·후속 응답 선택 → 저장·재편집. 총변형률·고유변형률·소성변형률을 같은 입력으로 취급하지 않는다.

**수정 파일·서비스 / 재사용 경로:** [신규] caelab/initial_field_conditions.py; [신규] apps/desktop_pre/initial_field_panel.py; [신규] caelab/adapters/initial_field_deck.py; 기존 apps/desktop_pre/commands.py 의 조건 연결(root hunk)

**의존:** B6.3.L02/L04 의 port 계약만 먼저 공유; constant field 로 독립 개발

**최소 확인 / 실패·취소 반례:** 자유 열팽창 αΔTL, 고정 열응력, 호환 affine 초기변형/응력의 첫 상태와 작은 증분. prescribed ε0 와 u0/σ0 불일치·T 와 ΔT 혼동은 차단. 원 pressure×area 합력 회귀 한 개.

**종료조건:** 지원표 INIT-THERMAL 의 세 의미가 실제 solver 상태/입력과 일치하고 나머지 원 조건을 손상시키지 않을 때 종료. plastic checkpoint 를 σ0 하나로 재구성하지 않음.


### B1.4.L03 — E5 병진·회전 spring/damper

**분류 D · 단독 책임 T1(CAD·조립·구조요소) · 상대 작업량 3/3**
원 연결: FN-12-01, FN-12-02; SPEC-PREFE-001(M/E/C/R/N/S), CONTACT-001, CAD-NUMERICAL-001.

**현재 구현 / 실제 잔여:** 기존 Windows OpenCourant pin `cb760c2`의 TYPE13 경로와 실제 elastic C3D4 FE patch/RBODY attachment 를 사용한다. 후보는 6 대각 k/c, 국부축, 실제 질량·관성과 FE 보존을 포함하나 native 인수는 미완료다.

**고정 지원 profile:** PRE, IMPACT (Windows pinned OpenCourant TYPE13)

**사용자 입력 → 조작 → 출력·저장재개:** 두 실제 점/영역과 오른손 국부축 선택 → 병진·회전 강성/감쇠 및 단위 입력 → 실제 C3D4 FE 의 RBODY attachment, 질량·관성·CoG 확인 → 지원 explicit transient 실행 → native 일반화 상대운동·힘/모멘트와 FE 변형 응답 확인 → 저장·새 owner 재열기.

**수정 파일·서비스 / 재사용 경로:** `_workspace/native-connector-delivery/` 후보와 기존 OpenCourant adapter. 공통 Core/schema/registry/provenance 는 root 가 통합한다. `_workspace/native-connector-reuse/CAE_IMPLEMENTATION_CONTRACT.md`와 구현자의 `CAE_DECISIONS.md` §8 계약을 유지한다.

**의존:** 기존 Runner 와 실제 C3D4 FE attachment. CCX 병진과 Aster 회전은 비교 대안이며 동시 필수 개발이 아니다.

**최소 확인 / 실패·취소 반례:** 6 대각 k-only/c-only/k+c 단위·방향·응답, `F=kδ`, `M=kθ`, positive inertia, 실제 FE patch, 초기운동·FE 질량 보존과 자유 감쇠의 native TH 를 확인한다. 해석해는 실제 fixture 의 질량·경계조건을 사용한다. TYPE13 의 평균회전/길이 결합을 단순 global Δu 나 독립 point spring 으로 해석하지 않는다.

**종료조건:** 입력→TYPE13/card·실제 부착→힘/모멘트·상대운동→저장/재열기가 native 인수와 일치할 때 닫는다. implicit static 또는 독립 Aster 6DOF spring 과 동등하다고 표시하지 않는다.

### B1.4.L04 — E6 조임→길이 유지→사용 하중

**분류 D · 단독 책임 T1(CAD·조립·구조요소) · 상대 작업량 3/3**
원 연결: FN-12-01, FN-12-02; SPEC-PREFE-001(M/E/C/R/N/S), CONTACT-001, CAD-NUMERICAL-001.

**현재 구현 / 실제 잔여:** 기존 실제 출력 CLOAD 600 N, 지지 FORC ±600 N, SOF −1200.021 N을 보존한다. 선택 절단면의 구조 절점력 합은 599.9996 N이며 지지력과 일치한다. SOF는 복구 응력의 면적분으로 재현됐고 중복 하중이나 reader 배율이 아니다. 이 정의를 구분한 결과 읽기와 편집·재열기를 연결한다. 원 실패 상태와 공학적 미승인 판정은 유지한다.

**고정 지원 profile:** PRE, Windows CCX 2.22 C3D10 pretension-section path; 실제 cut/RP, 단계별 native 제약은 owner/CAE 계약으로 고정한다.

**사용자 입력 → 조작 → 출력·저장재개:** 절단면과 축, 조임 force 또는 displacement 선택 → 단계별 hold/외력 → 선택 side 실제 cut node IDs 와 반대쪽 cut을 따로 읽기 → RP U1/reaction, SOF, cut FRD FORC 합, 복원 응력면적분을 구별해 표시 → 저장·cold reopen. 토크를 조임력으로 추정하지 않는다.

**수정 파일·서비스 / 재사용 경로:** 기존 contact_steps/pretension writer 와 native-03 source/output. 결과 meaning·MPC 제한은 현재 `_workspace/native-pretension-delivery/` owner/CAE record 가 정한다. 반대 cut 과 selected cut 의 혼합 합산을 금지한다.

**의존:** 기존 N3/CCX J2 계약, B1.4.L02 와 구속 의미 공유.

**최소 확인 / 실패·취소 반례:** 현재 CLOAD 600 N 및 지지 ±600 N, SOF −1200.021 N 의 차이를 지우지 않는다. 실제 선택 side 의 FRD FORC 를 exact node mapping 으로 합산하며 반대쪽은 별도 보존한다. RP U1/반력, SOF, cut force 및 복원 stress-area integral 은 별개 물리량이다. 원 acceptance 의 1e-5 상대 기준은 물리적으로 같은 양을 대조할 때만 유지하며, 다른 output channel 에 억지로 적용하지 않는다. 해당 정적·고립 절단면에서는 native 결과 소스가 구조 절점의 MPC 기여를 복원한 FORC를 사용한다. 전용 RP는 합에서 제외한다. 다른 구속·외력이 섞인 절단면이나 일반 접촉력으로 확대하지 않는다. 값이나 tolerance 를 바꾸어 통과시키지 않는다.

**종료조건:** native 조임→길이 유지→외력 continuation, actual cut/axis identity, 각 원출력의 물리적 의미, 결과 cold reopen 이 수용될 때 닫는다. SOF 는 정의와 일치하는 설명값으로만 쓰며 이름 바꾸기만으로 축력 판정하지 않는다.

### B1.5.L01 — C1 진짜 hard 접촉

**분류 D · 단독 책임 T2(접촉·비선형·동해석·충격·Runner) · 상대 작업량 3/3**
원 연결: FN-14-01, FN-14-03, FN-17-01; SPEC-PREFE-001(M/E/C/R/N/S), CONTACT-001, CAD-NUMERICAL-001.

**현재 구현 / 실제 잔여:** 현재 contact.law_errors 는 linear/tie 만 허용한다. Code_Aster benchmark contact 를 사용자 모델 지원으로 일반화해서는 안 된다.

**고정 지원 profile:** PRE, ASTER-HARD

**사용자 입력 → 조작 → 출력·저장재개:** 사용자 두 3D body 와 면집합 → hard/마찰 없음 또는 Coulomb 선택 → 독립 접촉 DOF/법선/초기 간극 확인 → 기존 JobManager 실행 → open/contact·gap·압력·마찰력 원값 → 저장·재열기/오류 수정.

**수정 파일·서비스 / 재사용 경로:** [신규] caelab/adapters/contact_aster_model.py; [신규] caelab/adapters/contact_aster_worker.py; [신규] caelab/adapters/contact_aster_results.py; contact.py/contact_deck.py/등록은 root 최소 hunk

**의존:** 기존 frozen mesh/sets; B1.6.L03 의 user Aster 공통 계약만, 구현 병렬

**최소 확인 / 실패·취소 반례:** 평면 두 body 압축·분리와 곡면 접촉 두 사용자 기하. 비관입/상보성의 길이·압력 잔차와 힘 평형, 마찰 stick/slip 를 native 규약으로 대조. penalty 확대를 hard 증거로 사용하지 않음.

**종료조건:** 17.4 hard formulation 의 실제 사용자 입력·출력·실패복구가 연결되고 독립 두 기하 기준을 통과. 설치되지 않은 PC 는 이 계산만 막음.


### B1.5.L02 — C2 implicit cohesive 와 압축 재접촉

**분류 D · 단독 책임 T2(접촉·비선형·동해석·충격·Runner) · 상대 작업량 3/3**
원 연결: FN-14-01, FN-14-03, FN-17-01; SPEC-PREFE-001(M/E/C/R/N/S), CONTACT-001, CAD-NUMERICAL-001.

**현재 구현 / 실제 잔여:** LAW117 explicit 경로는 있지만 implicit cohesive 지원이 아니다. 첫 implicit 조합을 별도로 구현해야 한다.

**고정 지원 profile:** PRE, ASTER-COH

**사용자 입력 → 조작 → 출력·저장재개:** 대향 HEXA8 bulk 의 quad face 에서 zero-thickness 3D_JOINT/HEXA8 을 명시 생성 → CZM_LIN_REG 의 SIGM_C, 단일 GC, PENA_ADHERENCE, PENA_CONTACT 와 방향 입력 → 개구·제하·압축·재개구 → native traction/비가역 임계상태/분리·압축 상태 선택 → 저장·재열기. 이 법칙에 독립 GI/GII 또는 BK 입력을 발명하지 않고, 별도 LAW117 의 GIC/GIIC 와 구별한다.

**수정 파일·서비스 / 재사용 경로:** [신규] caelab/implicit_interface.py; [신규] caelab/adapters/implicit_interface_aster.py; [신규] caelab/adapters/implicit_interface_results.py; [신규] apps/desktop_pre/implicit_interface_panel.py

**의존:** ASTER 공통 모델 계약; B1.5.L01 과 native 접촉 출력 의미 공유

**최소 확인 / 실패·취소 반례:** mode I 및 mixed opening/slip, κ0<κ<2GC/SIGM_C 의 부분 연화→압축→재개구 이력. GC 는 energy/area 이고 압축만으로 비가역 임계 κ가 증가하지 않아야 한다. κ의 비감소와 인장 강성 회복 금지, 원 내부변수와 에너지의 의미 대조. 동일 면에 joint 의 압축 penalty 와 독립 접촉을 중복 배치하지 않는다. 정규화된 임의 d 를 native 손상으로 만들지 않는다.

**종료조건:** 선정한 3D interface law 의 17.4 카탈로그·원채널을 실제 확인하고 계산/보존까지 완료. LAW117 실행 또는 미지원 문구로 대체 종료 불가.


### B1.5.L03 — C3 곡면·모서리·연쇄 tie 조정

**분류 D · 단독 책임 T2(접촉·비선형·동해석·충격·Runner) · 상대 작업량 3/3**
원 연결: FN-14-01, FN-14-03, FN-17-01; SPEC-PREFE-001(M/E/C/R/N/S), CONTACT-001, CAD-NUMERICAL-001.

**현재 구현 / 실제 잔여:** 기존 평면 projection 과 tie adjustment 를 재사용한다. 곡면 내부/경계/후행 master 이동의 완결 처리가 잔여다.

**고정 지원 profile:** PRE, CCX-TIE

**사용자 입력 → 조작 → 출력·저장재개:** TETRA10 의 명시 quadratic face A/B 와 이동 한계 → closest projection 후보/원좌표·조정좌표 미리보기 → A→B→C 순서 적용 → solver 가 실제 사용하는 초기좌표 확인 → 저장. 원 CAD/원 메시에는 덮어쓰지 않음.

**수정 파일·서비스 / 재사용 경로:** caelab/adapters/tie_adjustment.py; [신규] caelab/tie_chain.py; 기존 projection helper 와 contact inspector 재사용

**의존:** B3.2.L03 과 quadratic geometry 수식 공유하되 구현 소유는 T2; 동시 공동파일 편집 금지

**최소 확인 / 실패·취소 반례:** 곡면 내부·모서리 각각과 3body 비순환 chain. 상류 이동 후 후행 master 재계산; cycle/동거리 복수해/거리 초과는 거절. 실제 deck 좌표와 projection receipt 비교.

**종료조건:** 최대 3body 연쇄와 지정 face family 에서 미리보기·실제 조정·cold reopen 이 동일. 모호함을 nearest node 로 해소하지 않음.


### B1.5.L04 — C5 단계 활성과 접합 해제의 native 상태 연속

**분류 D · 단독 책임 T2(접촉·비선형·동해석·충격·Runner) · 상대 작업량 3/3**
원 연결: FN-14-01, FN-14-03, FN-17-01; SPEC-PREFE-001(M/E/C/R/N/S), CONTACT-001, CAD-NUMERICAL-001.

**현재 구현 / 실제 잔여:** CCX static linear MODEL CHANGE ADD/REMOVE 가 이미 있다. 재활성·tie release·재료 상태를 가진 단계 확장은 별도 잔여다.

**고정 지원 profile:** PRE, CONTACT-STAGES

**사용자 입력 → 조작 → 출력·저장재개:** 2–4 정적 단계에서 처음 tied → release → 필요 시 hard contact 활성 → 제하를 편집 → native 수락 상태를 이어 실행 → 각 단계 구속/접촉/반력과 원 실패 선택 → 저장. 해제 후 재접합 치유는 하지 않음.

**수정 파일·서비스 / 재사용 경로:** caelab/contact_activation.py; [신규] caelab/adapters/contact_stage_aster.py; 기존 contact_steps/단계 UI 의 확장은 root hunk

**의존:** B1.5.L01 hard; B1.6.L03 state continuation 계약

**최소 확인 / 실패·취소 반례:** 기존 CCX ADD/REMOVE 유지 회귀와 Aster tie 해제 1개. 단계 직전/직후 변위·응력·내부상태 참조, 제거된 구속 반력과 새 평형 확인. 실패를 새 무응력 모델로 재시작 금지.

**종료조건:** 삭제한 constraint 가 실제로 사라지고 유지한 state 는 그대로 이어지며 원 기록/편집 복원이 가능. 단순 단계 목록 저장으로 종료하지 않음.


### B1.5.L05 — C4 small/large sliding 과 실제 법선·쌍 교환

**분류 D · 단독 책임 T2(접촉·비선형·동해석·충격·Runner) · 상대 작업량 2/3**
원 연결: FN-14-01, FN-14-03, FN-17-01; SPEC-PREFE-001(M/E/C/R/N/S), CONTACT-001, CAD-NUMERICAL-001.

**현재 구현 / 실제 잔여:** 화살표 반전과 실제 native 면 방향/탐색 formulation 은 다르다. 이 선택이 효과적인 writer 와 결과 부호로 이어지는 부분을 고정한다.

**고정 지원 profile:** PRE, ASTER-HARD

**사용자 입력 → 조작 → 출력·저장재개:** 작은 미끄럼(초기 투영 근방) 또는 큰 미끄럼(현재 기하 재탐색)을 명시 → A/B·outward normal 확인/교환 → 접선 이동 → 동일 정의의 signed gap·tangent force 선택 → 저장/재열기.

**수정 파일·서비스 / 재사용 경로:** caelab/adapters/contact_aster_model.py [L01 소유자가 함께 수정]; [신규] apps/desktop_pre/contact_sliding_panel.py; contact_inspection.py 는 root 연결

**의존:** B1.5.L01 과 같은 T2 contact 작성자

**최소 확인 / 실패·취소 반례:** 작은 tangential 이동과 면 길이를 가로지르는 이동. 같은 물리 면의 A/B 교환 후 힘 부호/작용반작용 일치. small 허용 기하영역 밖에서는 잘못된 결과 대신 실행/설정 진단.

**종료조건:** 두 방법의 실제 native 기하 업데이트 정책·면 배향과 결과를 입증. 표시 전환만으로 닫지 않음.


### B1.5.L06 — C6 병진·회전 주기 경계의 지원 내 인수

**분류 A · 단독 책임 T2(접촉·비선형·동해석·충격·Runner) · 상대 작업량 2/3**
원 연결: FN-14-01, FN-14-03, FN-17-01; SPEC-PREFE-001(M/E/C/R/N/S), CONTACT-001, CAD-NUMERICAL-001.

**현재 구현 / 실제 잔여:** periodic_constraints 에 C3D10 static linear, 명시 proper rotation/translation 과 DOF1–3 방정식이 이미 있다.

**고정 지원 profile:** PRE, CCX-PERIODIC

**사용자 입력 → 조작 → 출력·저장재개:** 두 대응면과 주기축/각 또는 병진 선택 → 실제 노드·DOF correspondence 확인 → 실행 → 대응 U 와 반력 선택 → 저장. 회전 주기 공간 변환을 solid 의 회전 DOF4–6 으로 표시하지 않음.

**수정 파일·서비스 / 재사용 경로:** caelab/periodic_constraints.py; 관련 pre periodic 패널/기존 tests

**의존:** 없음; C1/C2 대기 불필요

**최소 확인 / 실패·취소 반례:** 평행 periodic 와 한 각도 sector, uB=R uA 및 mapped face force balance. 모호한 대응·같은 DOF 중복·stale mesh 거절.

**종료조건:** 현재 선언 조합의 Windows 조작·원 방정식·cold 결과가 일치. 다른 동적/소성 periodic 조합을 이번 필수로 추가하지 않음.


### B1.6.L01 — 새 implicit 조합의 pair 장·합력·기준점 모멘트

**분류 D · 단독 책임 T2(접촉·비선형·동해석·충격·Runner) · 상대 작업량 3/3**
원 연결: FN-14-02, FN-15-01, FN-15-02; SPEC-PREFE-001(M/E/C/R/N/S), CONTACT-001, CAD-NUMERICAL-001.

**현재 구현 / 실제 잔여:** 기존 CCX contact reader/resultants 와 explicit TH pair reader 는 있다. 새 hard/cohesive/단계 조합의 원 location·mask 를 같은 Post/응답 계약으로 연결하는 것이 잔여다.

**고정 지원 profile:** ASTER-HARD, ASTER-COH, CONTACT-STAGES, POST

**사용자 입력 → 조작 → 출력·저장재개:** 정확한 pair/side/increment 선택 → native 압력·gap/slip/status 와 one-sided force·기준점 moment 읽기 → 표/곡선/3D 같은 원 위치 → Numerical/Study 전달 → 저장/cold. 누락 출력·pair 미식별·실패 frame 을 구분.

**수정 파일·서비스 / 재사용 경로:** caelab/adapters/contact_aster_results.py [L01 작성자 재사용]; caelab/contact_resultants.py; [신규] caelab/contact_native_channels.py; Post 등록은 root

**의존:** B1.5.L01/L02/L04 의 채널 계약; reader 는 공개 native 형식 fixture 로 병렬 작성

**최소 확인 / 실패·취소 반례:** 한 절점에 두 pair 가 만나는 반례; side 두 번 합산 금지; 기준점 이동 M_new=M_old−Δr×F. 하중/반력 대조, 부분 출력 저장과 결과 읽기 무계산.

**종료조건:** 요구한 실제 제공 채널을 끝까지 읽고 파생 적분/원 채널을 구별. native 미제공 개별량은 원문 근거와 UNKNOWN, 필요한 주 결과 전체를 미지원으로 남기지는 않음.


### B1.6.L02 — 기존 J2+기하+linear/Coulomb 접촉 사용자 인수

**분류 A · 단독 책임 T2(접촉·비선형·동해석·충격·Runner) · 상대 작업량 2/3**
원 연결: FN-14-02, FN-15-01, FN-15-02; SPEC-PREFE-001(M/E/C/R/N/S), CONTACT-001, CAD-NUMERICAL-001.

**현재 구현 / 실제 잔여:** NS1 재료/제어/수렴 parser 와 실제 CCX 경로가 있다. 새 hard/cohesive 에 종속시키지 않는다.

**고정 지원 profile:** PRE, CCX-STATIC

**사용자 입력 → 조작 → 출력·저장재개:** 사용자 C3D10 specimen/지그에서 J2 table·NLGEOM·선형/Coulomb 접촉과 단계 편집 → 실행 → plastic state·수렴/거절 increment → 수정·새 run → 저장/cold.

**수정 파일·서비스 / 재사용 경로:** caelab/calculix_material.py; caelab/calculix_controls.py; caelab/calculix_convergence.py; 기존 contact_fem/deck·Runner

**의존:** 기존 NS1; Case B pretension 은 L04 이후 같은 scene 에서 추가

**최소 확인 / 실패·취소 반례:** 기존 수용 입력 재사용, 실제 변경 계수/마찰 한 번; 수렴 실패 원조건 반환과 마지막 수락 상태. 기존 tolerance/물리 기준 재사용, 전체 benchmark 반복 없음.

**종료조건:** 지원 조합의 실제 OS 입력·수렴/원 결과 선택·저장재개가 확인되면 닫음. 소성/접촉 자체 재개발 없음.


### B1.6.L03 — S2 Code_Aster 사용자 모델의 비선형 실행

**분류 D · 단독 책임 T2(접촉·비선형·동해석·충격·Runner) · 상대 작업량 3/3**
원 연결: FN-14-02, FN-15-01, FN-15-02; SPEC-PREFE-001(M/E/C/R/N/S), CONTACT-001, CAD-NUMERICAL-001.

**현재 구현 / 실제 잔여:** 17.4 J2·기하·contact benchmark workers 와 frozen TETRA10 linear user path 는 있다. benchmark 성공은 사용자 nonlinear 입력 실행이 아니다.

**고정 지원 profile:** PRE, ASTER-USER

**사용자 입력 → 조작 → 출력·저장재개:** 사용자 TETRA10/HEXA8 mesh·sets·등방재료·하중/구속 → linear/J2·기하 옵션과 지원 단계 확인 → 기존 Aster worker 에 제출 → 실제 수렴/절점·IP·재료상태 → 수정/실패재후처리·저장재개.

**수정 파일·서비스 / 재사용 경로:** caelab/adapters/codeaster_frozen.py; caelab/adapters/codeaster_frozen_worker.py; [신규] caelab/adapters/codeaster_user_nonlinear.py; 기존 codeaster_plasticity_worker/codeaster_geometric_worker 는 재사용

**의존:** 기존 frozen mesh registry; contact descriptor 계약만 먼저 공유

**최소 확인 / 실패·취소 반례:** 사용자 압축/인장 J2 specimen 와 큰 회전 탄성 기하 한 경로. native TETRA10 FPG5/IP·요소 ordering, stat continuation, 실패증분 보존. benchmark 고정 mesh 대신 사용자 mesh/sets 가 들어갔음을 확인.

**종료조건:** 정확한 17.4.0 runtime 에서 user FE 입력과 비선형 결과/오류/저장 연결을 확인하면 종료. Linux/SIF 와 Windows UI 를 구분.


### B2.1.L01 — U/V·밀도·감쇠의 실제 초기 상태

**분류 A · 단독 책임 T2(접촉·비선형·동해석·충격·Runner) · 상대 작업량 2/3**
원 연결: FN-12-02, FN-15-01, FN-15-02; SPEC-PREFE-001(NS2/N3), IMPACT-001.

**현재 구현 / 실제 잔여:** dynamic_model/calculix_dynamic 와 native 초기 U/V 입력은 이미 있다. static 선행과 비영 초기 U/V, dynamic tie 등 현재 거절 경계도 명시적이다.

**고정 지원 profile:** PRE, CCX-DYNAMIC

**사용자 입력 → 조작 → 출력·저장재개:** C3D10 body/DOF 선택 → 초기 U[mm]·V[mm/s]·밀도·Rayleigh 계수와 수치 α 편집 → 직접 transient → U/V/요청 채널과 실제 시간 선택 → 입력 수정/보존 결과 재열기.

**수정 파일·서비스 / 재사용 경로:** caelab/dynamic_model.py; caelab/calculix_dynamic.py; 기존 pre dynamic 패널·Simulation/Runner

**의존:** 기존 NS2; 신규 접촉법칙 불필요

**최소 확인 / 실패·취소 반례:** 작은 자유진동 두 초기 모드(U 또는 V), Rayleigh 와 알고리즘 감쇠 분리, 비영 IC/지정 DOF 충돌 및 밀도 단위 반례. 해석 주기/에너지 기준은 기존 값 유지.

**종료조건:** 실제 Windows CCX 의 첫 상태/시간곡선/오류 수정과 cold reopen 이 일치. 기존 dynamic 본체 재작성 없음.


### B2.2.L01 — 정적 preload→동적 상태 carry

**분류 A · 단독 책임 T2(접촉·비선형·동해석·충격·Runner) · 상대 작업량 2/3**
원 연결: ; SPEC-PREFE-001(NS2/N3), IMPACT-001.

**현재 구현 / 실제 잔여:** 기존 N3/NS2 단계 입력·native continuation 이 있다. 지원 J2/linear-contact 상태 연결의 최종 사용자 수용으로 관리한다.

**고정 지원 profile:** PRE, CCX-DYNAMIC

**사용자 입력 → 조작 → 출력·저장재개:** 정적 선행하중 후 dynamic 단계의 하중 유지/제거 선택 → 한 native 실행 → 경계 시각의 U/응력·소성상태와 후속 응답 → 실패 단계 설정 열기 → 저장/재개.

**수정 파일·서비스 / 재사용 경로:** caelab/contact_steps.py; caelab/calculix_dynamic.py; caelab/dynamic_results.py; 기존 pre freeze/dynamic editor

**의존:** B2.1.L01 계약; B1.6.L02 기존 J2

**최소 확인 / 실패·취소 반례:** 동일 모델의 유지와 제거 두 짧은 실행. 정적 하중계수와 실제 동적시간 구분; 초기화로 σ/state 가 소실되는 반례 확인. 주기/초기평형 비교.

**종료조건:** 지원된 같은 native 결과의 상태 연속성과 실패 보존이 확인되면 종료. tie/damper 의 임의 모든 동적 조합은 필수로 추가하지 않음.


### B2.3.L01 — 시간 stream·부분 실패·명시 재후처리

**분류 A · 단독 책임 T2(접촉·비선형·동해석·충격·Runner) · 상대 작업량 2/3**
원 연결: FN-15-02, FN-16-02, FN-25-01, FN-25-02; SPEC-PREFE-001(NS2/N3), IMPACT-001.

**현재 구현 / 실제 잔여:** dynamic_stream/results/locations/result store/recovery 와 Radioss 전용 recovery 가 있다. metadata-only 를 payload VERIFIED 로 오인하는 경계 등 기존 수정은 유지한다.

**고정 지원 profile:** CCX-DYNAMIC, IMPACT, POST

**사용자 입력 → 조작 → 출력·저장재개:** 원 실행의 frame/IP/응답·시각 선택 → 큰 결과의 필요한 frame 만 읽기 → 실패 raw 의 검증된 prefix/독립 frame 을 명시 재후처리 → 새 derived 선택·저장 → 원 store 없이 재열기.

**수정 파일·서비스 / 재사용 경로:** caelab/dynamic_native_stream.py; caelab/dynamic_results.py; caelab/dynamic_result_store.py; caelab/dynamic_recovery.py; caelab/impact_recovery.py (실제 파일 목록은 부록의 일치 경로 사용)

**의존:** 기존 readers; 새 채널은 해당 물리 leaf 소유

**최소 확인 / 실패·취소 반례:** 시간 중간 gap·잘린 tail·같은 크기 손상·Windows stat/fstat 차이·metadata-only 요청. 원 FAILED/coverage 유지, raw 불변, solver 호출 0; 모든 에너지를 IE 하나로 합치지 않음.

**종료조건:** 전체 파일 재로드 없이 정확 frame/선택과 새 derived 를 읽고 저장재개; native A 또는 native 분리에 없는 에너지는 계산값으로 합성하지 않음.


### B2.4.L01 — Windows WRITE→READ 실제 restart

**분류 A · 단독 책임 T2(접촉·비선형·동해석·충격·Runner) · 상대 작업량 3/3**
원 연결: FN-25-02; SPEC-PREFE-001(NS2/N3), IMPACT-001.

**현재 구현 / 실제 잔여:** dynamic_restart 와 rout/파일검증·continuation 본코드는 있다. 실제 같은 Windows build 의 WRITE/READ 인수가 남았다.

**고정 지원 profile:** CCX-DYNAMIC

**사용자 입력 → 조작 → 출력·저장재개:** 주어진 checkpoint 출력 주기 지정 → 정상 checkpoint 또는 명시 중단 → 같은 build/input/state 의 READ continuation → 원 연속 실행과 다음 시각부터 비교 → 새 attempt 와 continuation 관계 저장·재열기.

**수정 파일·서비스 / 재사용 경로:** caelab/dynamic_restart.py; caelab/dynamic_restart.py [존재 경로 확인 후 적용]; 기존 dynamic_result_store/JobManager

**의존:** B2.1/L02; 체크포인트 파일 형식과 runtime identity

**최소 확인 / 실패·취소 반례:** 작은 선형 한 모델의 continuous 대비 WRITE/READ, J2 상태 하나의 보존 확인. 잘린/다른 build/checkpoint·미확인 종료 거절. 출력 반올림 bound+기존 수치 tolerance 유지.

**종료조건:** 실제 native READ 가 소비한 checkpoint 와 결과 비교가 확인될 때만 종료. 설정 저장 또는 초기조건 rerun 을 restart 라고 표시하지 않음.


### B2.5.L01 — 계층 INP 의 기존 flat 물리 범위 합류

**분류 D · 단독 책임 T2(접촉·비선형·동해석·충격·Runner) · 상대 작업량 3/3**
원 연결: FN-16-01; SPEC-PREFE-001(NS2/N3), IMPACT-001.

**현재 구현 / 실제 잔여:** flat 입력은 여러 solid 와 COH3D8/LAW36 가 있으나 impact_assembly 계층은 elastic C3D4 에 한정된다. 계층 parser 를 다시 만들지 않고 물리·할당 범위를 합류시킨다.

**고정 지원 profile:** PRE, IMPACT-INP

**사용자 입력 → 조작 → 출력·저장재개:** PART/ASSEMBLY/INSTANCE·include 를 가진 사용자 입력 → 원 file/line/instance 와 할당 선택 → 재료·IC·TYPE24·출력 편집 → 변환 전후 mesh/PROP/IP/질량 검사 → Starter/Engine → Post → 같은 Simulation 저장재개.

**수정 파일·서비스 / 재사용 경로:** caelab/impact_assembly.py; [신규] caelab/impact_assembly_materials.py; caelab/impact_source.py; source editor; impact_model/adapters.impact 등록은 root/A 전용 hunk

**의존:** 기존 A 소유자 계속 유지; B2.6 bulk/LAW117 카드 helper 계약만

**최소 확인 / 실패·취소 반례:** 반복 instance 2개·nested include·다른 set 이름 충돌, C3D10 elastic 와 C3D8/R LAW36+COH3D8 각각 작은 입력. 미지원 card 누락 0, 원선택 계보, 명시 body 별 속도/ω와 높이 모드 구분.

**종료조건:** 평탄화 시 occurrence·재료/표면·IC 가 보존되고 현재 flat admission 과 같은 native 지원을 계층에서도 실제 실행/재열기. 임의 Abaqus 전체 문법은 범위 밖.


### B2.5.L02 — native RAD 의 LAW36/INIEVO·LAW117 명시 편집

**분류 D · 단독 책임 T2(접촉·비선형·동해석·충격·Runner) · 상대 작업량 3/3**
원 연결: FN-16-01; SPEC-PREFE-001(NS2/N3), IMPACT-001.

**현재 구현 / 실제 잔여:** impact_native 는 ELAST/TETRA4 중심, impact_native_b 는 exact TYPE24 TH 만 추가하고 bulk/interface controls 를 거절한다. B native 편집이 이미 있다는 이유로 전 범위를 닫지 않는다.

**고정 지원 profile:** IMPACT-RAD

**사용자 입력 → 조작 → 출력·저장재개:** Starter/Engine/includes 열기 → PART/MAT/PROP/SOLID/INTER 와 원줄 영향 선택 → 보존 LAW36/INIEVO 또는 LAW117 설정을 명시 수정 → 카드/세트/단위 검사 → 기존 pinned runtime → 손상·활성·시간 결과 → 동일 owner 저장재개.

**수정 파일·서비스 / 재사용 경로:** caelab/impact_native.py; caelab/impact_native_b.py; [신규] caelab/impact_native_material_cards.py; caelab/impact_rad_source.py; A/root writer 접점만 분리

**의존:** B2.6.L01–L03 의 물리 profile; reader/원문편집 병렬 가능

**최소 확인 / 실패·취소 반례:** 한 native bulk 와 한 interface 입력. 미지원 include/card 를 몰래 삭제하지 않음; 원파일 수정 영향과 effective deck 정확 비교; 간극/단위/실패카드 상호충돌을 실행 전 검출.

**종료조건:** B 의 고정 법칙·요소 조합을 native RAD 에서도 선택·편집·실행·복구할 수 있음. 모든 Radioss card 지원을 요구하지 않음.


### B2.6.L01 — LAW36/INIEVO 실제 손상·삭제·에너지 인수

**분류 A · 단독 책임 T2(접촉·비선형·동해석·충격·Runner) · 상대 작업량 3/3**
원 연결: FN-16-02, FN-17-01, FN-17-02; SPEC-PREFE-001(NS2/N3), IMPACT-001.

**현재 구현 / 실제 잔여:** impact_bulk/deck/history/results 의 카드·1IP·ILEN0·Gf·source state·reader 는 있다. runtime 조합 수용을 카드 존재와 혼동하지 않는다.

**고정 지원 profile:** IMPACT-BULK

**사용자 입력 → 조작 → 출력·저장재개:** 교정된 initiation map/Gf·rate 범위와 body 선택 → 부족값 UNKNOWN 검토 → fixed profile 실행 → native damage/active/deletion·element IE density 와 개별 energy 선택 → 실패 재후처리·cold reopen.

**수정 파일·서비스 / 재사용 경로:** caelab/impact_bulk.py; caelab/impact_bulk_deck.py; caelab/impact_bulk_history.py; caelab/impact_bulk_results.py; 기존 bulk 전용 tests

**의존:** 기존 flat INP 로 바로 인수 가능; 계층/RAD 전체를 대기하지 않음

**최소 확인 / 실패·취소 반례:** 단요소와 두 요소의 사전 지정 두 길이·두 timestep 비교만. 실제 PROP/IP/FAILIP, Gf/L/단위, eta clamp/rate 경로와 삭제 확인. 온도 의존·damage dissipation 없는 채널 생성 금지.

**종료조건:** 지원 조합의 실제 native S/state/damage/deletion/energy 및 보존값을 확인하면 종료. native 없는 개별 손상소산 UNKNOWN 은 유지하되 카드/손상 주 경로 미실행은 종료 불가.


### B2.6.L02 — LAW117 부분 손상 unload–compression–reopen

**분류 D · 단독 책임 T2(접촉·비선형·동해석·충격·Runner) · 상대 작업량 3/3**
원 연결: FN-16-02, FN-17-01, FN-17-02; SPEC-PREFE-001(NS2/N3), IMPACT-001.

**현재 구현 / 실제 잔여:** positive-thickness LAW117 envelope/부피밀도/paired opening 과 mean damage 는 있다. d 가 0 과 1 사이인 반복 이력·압축 분기 편집/관측 수용은 미완결이다.

**고정 지원 profile:** IMPACT-INTERFACE

**사용자 입력 → 조작 → 출력·저장재개:** 실제 loading history 와 Isym/압축 규약을 명시 → 0<d<1 까지 개구 → 제하·압축·재개구/mixed mode → native traction/손상·paired opening·bulk 상태 선택 → 같은 이력/원출력 저장.

**수정 파일·서비스 / 재사용 경로:** caelab/impact_interface.py; caelab/impact_damage.py; [신규] caelab/impact_interface_history.py; native loading/출력 연결은 A/root hunk

**의존:** 기존 LAW117 카드; B2.5.L02 의 editor 연결은 병렬

**최소 확인 / 실패·취소 반례:** 부분 손상 한 loop 와 mixed-mode loop 한 개. 손상 비감소·잔존강성/재개구 envelope·압축 부호, cohesive 와 별도 TYPE24 의 압축 중복 0. 무손상 loop 만으로 통과 금지.

**종료조건:** 정확한 fixed-source 법칙/압축 분기를 실행하고 partial state 이력을 보존. cyclic fatigue 로 재명명하지 않음.


### B2.6.L03 — 완전 삭제 후 bulk-face 재접촉·재개구

**분류 D · 단독 책임 T2(접촉·비선형·동해석·충격·Runner) · 상대 작업량 3/3**
원 연결: FN-16-02, FN-17-01, FN-17-02; SPEC-PREFE-001(NS2/N3), IMPACT-001.

**현재 구현 / 실제 잔여:** 현재 explicit start-time gate/후처리 위반 검사는 자동 삭제 연동이 아니다. 완전 삭제 뒤 actual contact 와 이중 압축 방지의 state 정책이 잔여다.

**고정 지원 profile:** IMPACT-INTERFACE

**사용자 입력 → 조작 → 출력·저장재개:** 계면 완전 삭제 → 살아 있는 대향 bulk face 의 실제 TYPE24 contact → 압축/재개구 → contact pair force/gap·활성·계면 삭제를 따로 선택 → 실패 포함 저장재개.

**수정 파일·서비스 / 재사용 경로:** caelab/impact_interface.py [L02 와 같은 단독 작성자]; [신규] caelab/impact_reclosure_policy.py; pinned TYPE24/LAW117 deck 설정은 root hunk

**의존:** B2.6.L02·실제 pair reader. 삭제 trigger/접촉 gap 의 fixed-source 확인은 이 행 개발에 포함

**최소 확인 / 실패·취소 반례:** 계면 완전파손 후 compression→opening 한 이력, bulk 중 하나까지 삭제되는 반례. cohesive traction 부활 0; 전 증분에서 겹치는 압축지지 금지. animation 표본만으로 native 전 증분 성공 주장 금지.

**종료조건:** 핀 runtime 에서 전환 정책과 실제 bulk 재접촉을 입증할 때 종료. 시간 지연만 설정한 현 경로를 완료로 삼지 않음. 새로운 solver 도입/자동 pin 변경은 금지.


### B2.6.L04 — pair force·표본 impulse·질량·에너지의 최종 선택 연결

**분류 A · 단독 책임 T2(접촉·비선형·동해석·충격·Runner) · 상대 작업량 2/3**
원 연결: FN-16-02, FN-17-01, FN-17-02; SPEC-PREFE-001(NS2/N3), IMPACT-001.

**현재 구현 / 실제 잔여:** 현재 기록에 TH18 응답×150 표본과 저장재개가 있다. native 원량, converter 의미, sample trapezoid 를 혼합하지 않은 사용자 동선만 남긴다.

**고정 지원 profile:** IMPACT, POST

**사용자 입력 → 조작 → 출력·저장재개:** pair/side·signed component·시간구간을 선택 → raw TH 또는 animation 원행과 gap 확인 → 명시 표본 적분/개별 energy 읽기 → Study/Plan 전달 → 원 raw 없이도 보존 결과 cold read.

**수정 파일·서비스 / 재사용 경로:** caelab/impact_responses.py; caelab/adapters/impact_timing.py; caelab/impact_bulk_history.py; 기존 contact/pair Qt

**의존:** 기존 실제 pair 결과 재사용; 새물리 L01–L03 의 추가채널은 그 leaf 에서 검사

**최소 확인 / 실패·취소 반례:** 기존 150 표본 reuse, interval endpoint/gap/nonmonotonic/중복시각 반례. added/original mass, element density/total IE, native impulse/derived N·s 를 별도 metadata 로 확인.

**종료조건:** 같은 pair/source/time/mask/단위로 선택·전달·cold read. converter source NOT_PROVEN 을 source-proven 으로 승격하지 않음.


### B2.6.L05 — 기존 ε–N·SWT·critical-plane 피로의 실제 작업 인수

**분류 A · 단독 책임 T2(접촉·비선형·동해석·충격·Runner) · 상대 작업량 2/3**
원 연결: FN-16-02, FN-17-01, FN-17-02; SPEC-PREFE-001(NS2/N3), IMPACT-001.

**현재 구현 / 실제 잔여:** fatigue_strain/tensor/life 에 CMB, uniaxial SWT, normal-strain sampled-plane SWT 와 cycle lineage 가 있다. 기존 SN/rainflow 도 유지; 새 다축 엔진을 처음부터 만들지 않는다.

**고정 지원 profile:** FATIGUE

**사용자 입력 → 조작 → 출력·저장재개:** 동시 stress/total-strain tensor CSV 또는 보존 결과 → 위치·시간·frame·shear·교정범위/방법 확인 → plane→cycle→원행 선택 → 결과 저장·새 process 읽기. 평가면 분해능을 명시.

**수정 파일·서비스 / 재사용 경로:** caelab/fatigue_strain.py; caelab/fatigue_tensor.py; caelab/fatigue_life.py; 관련 전용 fatigue Qt/tests

**의존:** 기존 공개 동시 tensor 이력으로 독립 인수; 새 damage native 실행 대기 불필요

**최소 확인 / 실패·취소 반례:** 교정 범위 안의 단축 반전+CMB/SWT 독립 기준, 회전된 동일 다축이력의 frame 변환, 시간/shear 불일치·미교정 반례. planes sampled vs continuous optimum 구분.

**종료조건:** cycle·수명·실패/미평가·calibration provenance 와 선택/저장재개가 일치. LAW117 반복 손상을 수명으로 대체하지 않음.


### B3.1.L01 — 실제 ParaView 주창·선택 설정의 OS 작업 인수

**분류 A · 단독 책임 T3(Post·비교·측정) · 상대 작업량 2/3**
원 연결: FN-27-01, FN-27-02; SPEC-POST-COMPARE-001, POST-NUMERICAL-001, DESKTOP-001/002.

**현재 구현 / 실제 잔여:** 이전 GUI 설계가 최신 PRODUCT_PLAN 과 post_window/settings pages 에 반영되어 있다. 다시 전체 화면을 설계하지 않는다.

**고정 지원 profile:** W, POST

**사용자 입력 → 조작 → 출력·저장재개:** 외부 VTU/PVD 열기 → native source/field/time/점 선택 → 작은 비모달 Qt 에서 해당 분석만 정의 → preview/apply → native View/표/곡선 → 저장/재개 → 관측 전달. 1440×900 과 좁은 창에서 실행.

**수정 파일·서비스 / 재사용 경로:** apps/research/post_window.py; apps/research/post_measurement_dialog.py; apps/desktop_post/workspace.py; 기존 commands/navigation

**의존:** 없음; stock ParaView 로 먼저 닫음. SDK L02 대기는 해당 close 경로만

**최소 확인 / 실패·취소 반례:** 한점 값·이력·비교 각각 한 개, 미결정단위/미적용/실패/늦은응답·취소. 실제 OS focus/Enter/Esc/Undo/선택과 원 source 일치; 정적 그림을 3D 로 표시 금지.

**종료조건:** 현재 구현된 주 작업 동선에 긴 전체 폼·동급 버튼 나열·내부 ID 강요가 없고 실제 조작/저장재개가 확인되면 종료.


### B3.1.L02 — managed ParaView 저장·File→Exit 네 경로

**분류 A · 단독 책임 T7(독립 실행·연결·이동사본·Windows 배포) · 상대 작업량 3/3**
원 연결: FN-27-01, FN-27-02; SPEC-POST-COMPARE-001, POST-NUMERICAL-001, DESKTOP-001/002.

**현재 구현 / 실제 잔여:** 관리 close 플러그인/SDK 배포 작업과 bridge 저장 관문은 별도 진행 중이다. SDK C++/binary 원문은 이 Python ZIP 에 없으므로 빌드 완료·설치 성공을 주장하지 않는다.

**고정 지원 profile:** W, POST-SDK

**사용자 입력 → 조작 → 출력·저장재개:** 변경된 native/Qt 정의에서 Ctrl+S, 창 X, Alt+F4, File→Exit → 저장/버리기/취소 선택 → 실제 저장 acknowledgment → 종료 또는 편집 유지 → 새 owner 재개.

**수정 파일·서비스 / 재사용 경로:** apps/desktop_post/commands.py; apps/desktop_post/workspace.py; 기존 native SDK close plugin/Windows packaging(패킷 밖, 재구현 지시 아님)

**의존:** 호환 SDK artifact 수용과 B8.6.L01 의 해당 설치 경로만

**최소 확인 / 실패·취소 반례:** 네 진입을 같은 gate 로 연결, Qt 미전송편집·native dirty·쓰기 실패·응답 유실·취소·종료 미확인을 구별. failure 에서창유지, 없는 embed API 사용 0.

**종료조건:** 실제 호환 ParaView 에서 네 경로가 같은 문서/저장 결과를 지킴. CI PASS 만으로 닫지 않음; 외부 장비 조건으로 넘기지 않음.


### B3.2.L01 — 네 원응력→공통 Cauchy 비교

**분류 A · 단독 책임 T3(Post·비교·측정) · 상대 작업량 2/3**
원 연결: FN-28-01, FN-28-02; SPEC-POST-COMPARE-001, POST-NUMERICAL-001, DESKTOP-001/002.

**현재 구현 / 실제 잔여:** 명시 F/J 와 원응력 측도를 이용한 Cauchy·Kirchhoff·PK1·PK2 변환 및 B−A 비교 연결은 `e76cde6`에서 통합됐다. 재개발 배정은 없다. 남은 일은 정확한 Post field·위치·시간 선택, 저장 lineage 와 cold 사용자 인수다.

**고정 지원 profile:** POST, STRESS-CONVERT

**사용자 입력 → 조작 → 출력·저장재개:** A/B 의 원 field, F/J, basis, 시각, 위치와 시간·공간 대응을 선택 → 원응력을 공통 Cauchy 로 변환 → Δ/percent/mask 와 원값 검토 → 저장 후 새 프로세스에서 같은 선택을 연다. full P 의 비대칭 성분과 원 F/J 계보를 보존한다.

**수정 파일·서비스 / 재사용 경로:** `e76cde6`의 기존 응력변환; `apps/desktop_post/comparison_native.py`; 기존 비교 owner/schema. 완료 코드를 다시 쓰지 않고 확인된 인수 결함만 수정한다.

**의존:** 원 source/CAE 자문 계약. 새 strain measure 와 고차 공간 mapper 는 L02/L03 에서 각각 인도하며 이 leaf 의 재개발 선행조건이 아니다.

**최소 확인 / 실패·취소 반례:** 같은 물리 σ에서 구성한 네 입력과 비정방 F·회전기저를 독립 기준과 대조한다. J≤0, 성분 누락, F/J 불일치는 거절한다. 성분 변환 후 norm 과 norm 차이를 구분하고 원값·mask·revision 을 저장/재열기한다.

**종료조건:** 네 측도의 공통 Cauchy 값과 F/J 계보·mask·원 A/B 선택이 독립 기준 및 cold reopen 에서 일치하면 종료한다. 통합된 코드는 재개발하지 않는다.

### B3.2.L02 — 변형률의 유한한 측도 비교

**분류 D · 단독 책임 T3(Post·비교·측정) · 상대 작업량 2/3**
원 연결: FN-28-01, FN-28-02; SPEC-POST-COMPARE-001, POST-NUMERICAL-001, DESKTOP-001/002.

**현재 구현 / 실제 잔여:** 동일 strain measure/기저 변환은 재사용한다. 서로 다른 strain tensor 의 물리 변환은 응력 변환과 다른 계산이다.

**고정 지원 profile:** POST, STRAIN-CONVERT

**사용자 입력 → 조작 → 출력·저장재개:** Green–Lagrange E, Euler–Almansi e, material Hencky H 중 source 선언과 필요한 F 선택 → 공통 reference E 로 변환·원 측도 검토 → 비교/선택/저장. 소변형 ε를 유한변형 E 로 이름만 바꾸지 않음.

**수정 파일·서비스 / 재사용 경로:** [신규] caelab/post_strain_measures.py; 기존 비교 전용 helper; common comparison schema 는 root

**의존:** B3.2.L01 의 F/J/위치 계약 공유만

**최소 확인 / 실패·취소 반례:** 단축 및 회전·전단 F, E=(FᵀF−I)/2, E=FᵀeF, E=(exp(2H)−I)/2 의 독립 대조. 필요 F/대칭성/양의 stretch 미확인 시 계산 차단, side-by-side 보존.

**종료조건:** 세 선언 측도 범위와 mask/원행/저장재개가 연결되면 종료. 임의 strain 명·unknown deformation 의 보편 변환은 추가하지 않음.


### B3.2.L03 — TET/HEX 고차 공간 비교

**분류 D · 단독 책임 T3(Post·비교·측정) · 상대 작업량 3/3**
원 연결: FN-28-01, FN-28-02; SPEC-POST-COMPARE-001, POST-NUMERICAL-001, DESKTOP-001/002.

**현재 구현 / 실제 잔여:** 현재 same_mesh 또는 linear_tetra_b_to_a 만 admit 한다. 생산되는 TETRA10 및 expanded HEX20/HEX8 를 소비하는 명시 보간이 잔여다.

**고정 지원 profile:** POST, SPATIAL

**사용자 입력 → 조작 → 출력·저장재개:** 원 A/B 위치·mesh/필요영역 선택 → 선형/2차 TET 또는 HEX native shape-function B→A 보간 → inside/failed inversion/coverage·원 B cell 확인 → 변환 후 차이 → 저장재개.

**수정 파일·서비스 / 재사용 경로:** [신규] caelab/post_spatial_mapping.py; apps/desktop_post/comparison_native.py; caelab/field_transfer_contract.py; 기존 linear mapper 재사용

**의존:** B3.2.L01/L02 와 연산순서만 공유; manufactured fields 로 병렬

**최소 확인 / 실패·취소 반례:** 상수/선형 및 해당 차수 다항 field; affine TET10/HEX20 와 유효 curved cell 한 개. 뒤집힘·복수 포함·외삽·midside 오류 거절. ID 를 값처럼 보간하지 않음.

**종료조건:** 표 SPATIAL 의 네 volume family 에서 실제 B 원 위치와 interpolation metadata 를 보존. 보간 성공을 보존적 transfer 라 부르지 않음.


### B3.3.L01 — 고차면 측정

**분류 D · 단독 책임 T3(Post·비교·측정) · 상대 작업량 2/3**
원 연결: FN-14-02, FN-27-01; SPEC-POST-COMPARE-001, POST-NUMERICAL-001, DESKTOP-001/002.

**현재 구현 / 실제 잔여:** TRI6/QUAD8의 고정 기준 면 평균·적분, 수치 차이·미확정 표시, 선택 저장과 Data/계획 연결을 통합했다. 저장된 면/두 점 시간 이력의 곡선 비교 연결도 포함한다. OS 직접 조작과 나머지 지원 한계의 현재 판정은 CURRENT_STATE를 따른다.

**고정 지원 profile:** POST, SURFACE

**사용자 입력 → 조작 → 출력·저장재개:** 같은 dataset 의 고차 face/응답 선택 → reference 면적 가중 평균·적분 정의 → quadrature/유효 영역 preview → native 표/곡선 → 같은 선택 저장.

**수정 파일·서비스 / 재사용 경로:** apps/desktop_post/measurements.py; [신규] apps/desktop_post/surface_quadrature.py; 기존 sample reader

**의존:** 기존 measurement 정의/단위; B3.2.L03 기하 수식 공유만

**최소 확인 / 실패·취소 반례:** 평면 TRI6/QUAD8 의 상수·선형 적분, 곡면 patch 의 두 quadrature order 비교. midside/normal/빈영역·invalid 값 반례. recovered field 는 recovered 라는 표기 보존.

**종료조건:** 고차 형상과 실제 field association 을 사용하고 면적·응답 단위·오차/미확정이 보존되면 종료.


### B3.3.L02 — 다중 block 측정·원 leaf 복귀

**분류 D · 단독 책임 T3(Post·비교·측정) · 상대 작업량 2/3**
원 연결: FN-14-02, FN-27-01; SPEC-POST-COMPARE-001, POST-NUMERICAL-001, DESKTOP-001/002.

**현재 구현 / 실제 잔여:** ParaView6.2 Assembly/BlockSelectors 원복 helper 는 있다. 측정 대상 자체의 여러 leaf 수집/중복·mask 처리는 단일 dataset 한계 밖이다.

**고정 지원 profile:** POST, MULTIBLOCK

**사용자 입력 → 조작 → 출력·저장재개:** 복합 dataset 에서 명시 leaf 집합과 field/time 선택 → leaf 별 측정/선택 또는 명시 합/면적평균 → 원 leaf·row·component 복귀 → 저장·새 PV 재개.

**수정 파일·서비스 / 재사용 경로:** [신규] apps/desktop_post/measurement_blocks.py; apps/desktop_post/measurements.py; 기존 origin-return helper

**의존:** B3.3.L01 과 독립 linear face 로 먼저 구현; layer/part aggregation 의미 공유

**최소 확인 / 실패·취소 반례:** 동일 이름 배열/점 ID 가 다른 두 leaf, ghost/shared face·빈 leaf·혼합 component 반례. 동일좌표를 자동 병합하지 않고 명시 lineage 로만 중복 제거.

**종료조건:** leaf path·nativeID·mask 와 aggregation 정의가 exact cold selection 까지 유지. 단일 leaf 를 전체 composite 로 오인하지 않음.


### B3.3.L03 — 실제 현재 형상 면적·법선으로 측정

**분류 D · 단독 책임 T3(Post·비교·측정) · 상대 작업량 2/3**
원 연결: FN-14-02, FN-27-01; SPEC-POST-COMPARE-001, POST-NUMERICAL-001, DESKTOP-001/002.

**현재 구현 / 실제 잔여:** 현재 fixed-reference geometry 측정을 재사용한다. Warp 표시 배율을 실제 면적 변화로 사용하지 않는 current-geometry 경로가 잔여다.

**고정 지원 profile:** POST, SURFACE

**사용자 입력 → 조작 → 출력·저장재개:** X 와 실제 U/F·좌표단위/시각을 선택 → X+u 또는 원 current geometry 에서 면적/법선 확인 → current-area 평균·적분/이력 → reference 결과와 나란히 보기 → 저장.

**수정 파일·서비스 / 재사용 경로:** [신규] apps/desktop_post/measurement_geometry_state.py; 기존 surface_quadrature/measurement_histories 접점

**의존:** B3.3.L01; multiblock 은 L02 완료 뒤 동일 계약으로 소비

**최소 확인 / 실패·취소 반례:** 균일 2 축 stretch 의 면적배율과 rigid rotation, 뒤집힘/누락 U/표시배율 100 반례. 물리 시각별 실제 면적 사용; 새면적 없이 전시각 면적 재사용 금지.

**종료조건:** reference/current 두 모드의 실제 면적·normal·mask·원시각과 곡선이 보존되면 종료.


### B3.4.L01 — 원 결과 복구·변경 branch·정확한 원 선택 반환

**분류 A · 단독 책임 T3(Post·비교·측정) · 상대 작업량 2/3**
원 연결: FN-14-03, FN-28-03; SPEC-POST-COMPARE-001, POST-NUMERICAL-001, DESKTOP-001/002.

**현재 구현 / 실제 잔여:** source repair/change, measurement/curve origin return 과 retained Report image 검증은 있다. 새로운 복구 store/renderer 를 만들지 않는다.

**고정 지원 profile:** POST, W

**사용자 입력 → 조작 → 출력·저장재개:** 같은 bytes 이동 파일 다시 연결 / 다른 bytes 새 B branch 를 구분 → 기존 A/옛결과 유지 → Plan·Study·Report 에서 해당 원 leaf/frame/component 열기 → 선택 복귀·저장재개.

**수정 파일·서비스 / 재사용 경로:** apps/desktop_post/source_repair.py; apps/desktop_post/source_change.py; 기존 curve_origin/measurement_open/report_image helpers

**의존:** 기존 기능으로 독립 인수; B7.5.L01 은 완성 Report 배치/출력만 별도

**최소 확인 / 실패·취소 반례:** 동일경로 내용변경·같은내용 경로이동·multiblock leaf 선택 복귀·원파일부재 보존자산. provider/solver 재호출 0; 실패 시 기존표/선택의 stale 표기.

**종료조건:** 정확 원자료 복구/branch/선택 반환의 마지막 GUI/cold 왕복이 확인되면 종료; B7.5 에서 같은 return 코드를 이중 개발하지 않음.


### B4.1.L01 — 처리 recipe·재표본 계보·큰 Data 작업 인수

**분류 A · 단독 책임 T4(Data·Material·구성식 FE) · 상대 작업량 2/3**
원 연결: FN-04-01, FN-04-02, FN-04-03; SPEC-RESEARCH-003(FN03/04/06/07/09), EXPERIMENT-001, NUMERICAL-002.

**현재 구현 / 실제 잔여:** data_processing 과 document/dialog, raw/derived sample lineage·mask 단계·Plan 편입이 있다. 1000행 preview 를 전체 처리 상한으로 판단하지 않는다.

**고정 지원 profile:** W, DATA

**사용자 입력 → 조작 → 출력·저장재개:** CSV/ASCII 두 시험 → 열·역할·단위 선택 → 교정/순서 있는 처리·필터/재표본화 preview → 같은 sample 의 원행/구간/가중치 확인 → 적용·Plan train/holdout 편입 → 저장·새 owner 재개.

**수정 파일·서비스 / 재사용 경로:** caelab/data_processing.py; caelab/data_processing_document.py; caelab/numerical_fit_lineage.py; apps/research/data_processing_dialog.py

**의존:** 없음; B7.3 은 uncertainty 추가 연결만 병렬

**최소 확인 / 실패·취소 반례:** 불규칙 시각/NaN/gap·품질제외를 가로지르는 보간 차단, 재표본 train/holdout 이 원행을 공유하는 반례. 1000행 초과 파일에서 표 preview 와 실제처리 수가 다름을 확인; 편집마다 전체 reload 없음.

**종료조건:** raw 와 파생 lineage·mask 순서·Plan inclusion·cold read 가 원행까지 이어지고 기준 수치/실패를 보존하면 종료.


### B4.2.L01 — 단축·동축 유한변형 관측→같은 측도 예측

**분류 A · 단독 책임 T4(Data·Material·구성식 FE) · 상대 작업량 2/3**
원 연결: FN-03-01, FN-03-02, FN-06-01; SPEC-RESEARCH-003(FN03/04/06/07/09), EXPERIMENT-001, NUMERICAL-002.

**현재 구현 / 실제 잔여:** 기존 finite_measure_*·prediction·Plan 엔진을 재사용해 단축·동축의 실제 관측/예측 사용자 흐름을 인수했다. 기존 공개 합성 case02의 fit·holdout 각6표본과 후보 actual F/J, 원 mask/weight/scale, 실제 채택 receipt/저장·별도 cold를 보존했다. UI에서 law/측도/단위·원행/clock·치수/근거·관측 J와 명시 가정을 구분하고 현재 원 Material 변경의 확정 거절을 확인했다. [사용법과 실제 화면](FINITE_MEASURE_WORKFLOW_KO.md). 새 피팅/법칙/solver/provider 실행은 없으며 실장비 crosshead 등가성과 공학 qualification은 별도 미확인이다.

**고정 지원 profile:** W, MATERIAL

**사용자 입력 → 조작 → 출력·저장재개:** force/gauge 또는 crosshead 채널·A0/L0/current A 또는 F/J 입력 → 원행 alignment·stress/strain measure 확인 → 같은 관측량 예측 → fit/holdout·명시 채택 → 저장재개.

**수정 파일·서비스 / 재사용 경로:** caelab/finite_measure_protocol.py; caelab/finite_measure.py [정확 패킷 경로 대조]; caelab/material_test.py; tests/finite_measure

**의존:** B4.1 의 보존 source 재사용

**최소 확인 / 실패·취소 반례:** P11=force/A0, σ11=(λ1/J)P11, logλ 유효 조건. 현재면적/J 누락, λ≤0, crosshead≠gauge, 시간순서·단위 반례. 예제 물성을 default 로 넣지 않음.

**종료조건:** 지원 관측→법칙예측→잔차/독립 holdout·채택·새 process 까지 원 측도/단위가 동일하면 종료.


### B4.3.L01 — 혼합 F/stress 제어의 법칙별 인수

**분류 A · 단독 책임 T4(Data·Material·구성식 FE) · 상대 작업량 2/3**
원 연결: FN-06-01, FN-06-02, FN-07-01; SPEC-RESEARCH-003(FN03/04/06/07/09), EXPERIMENT-001, NUMERICAL-002.

**현재 구현 / 실제 잔여:** material_control 과 law_native_history 의 trial 격리/수락 state 가 있다. 자유 횡수축을 고정 F22=F33=1 로 대체하지 않는다.

**고정 지원 profile:** W, MATERIAL, LAW-FE

**사용자 입력 → 조작 → 출력·저장재개:** prescribed F, measured transverse, 또는 축 F+횡 stress target 선택 → 동일 마지막 수락 state 에서 Newton trial → 실제 target residual·내부상태·실패증분 → Plan 평가/보존/cold.

**수정 파일·서비스 / 재사용 경로:** caelab/material_control.py; caelab/material_test.py; 기존 law_native_history 의존모듈(패킷 일부 누락, 런타임 원문 확인 필요); material protocol UI

**의존:** 기존 point adapters; B6.1.L01 custom FE 대기 불필요

**최소 확인 / 실패·취소 반례:** Neo-Hooke 축 F+횡응력 0, DP smallstrain 의 허용 제어, Maxwell 실제 time 증분. 실패 trial 뒤 같은 초기 state 에서 다시 평가하여 오염 0; 원 tolerance 사용.

**종료조건:** 법칙이 실제 지원하는 성분/측도 표와 free/constrained 결과 차이·초안/저장/실패가 일치하면 종료. 임의 모든 tensor mixed-control 을 추가하지 않음.


### B4.4.L01 — 후보 상세 보존·새 평가·채택 충돌

**분류 A · 단독 책임 T4(Data·Material·구성식 FE) · 상대 작업량 2/3**
원 연결: FN-04-03, FN-07-02, FN-07-03; SPEC-RESEARCH-003(FN03/04/06/07/09), EXPERIMENT-001, NUMERICAL-002.

**현재 구현 / 실제 잔여:** numerical_candidate_detail/evidence 와 결과창·owner CAS 가 있다. 모든 후보의 상세를 무조건 재계산하는 새 정책을 만들지 않는다.

**고정 지원 profile:** W, DATA, NUM

**사용자 입력 → 조작 → 출력·저장재개:** 보존/미보존/실패 후보를 선택 → 정확한 상세 곡선·holdout 열기 → 필요한 경우 명시 새 evaluation → 비교/채택 제안 → 현재 owner 변경과 충돌 검토 → 새 revision 저장/재열기.

**수정 파일·서비스 / 재사용 경로:** caelab/numerical_candidate_detail.py; caelab/numerical_candidate_evidence.py; apps/research/candidate_results_window.py; 기존 result_return/owner 는 root

**의존:** 기존 Numerical Plan; 관련 저장 B8.2 와 receipt 계약 공유

**최소 확인 / 실패·취소 반례:** 상세미보존/holdout 미평가 표기, 선택·재열기 실행 0, 명시상세만새 ID. 다른 owner 가같은계수변경한 CAS 반례와 실제채택근거 assetscoldread.

**종료조건:** 채택·비교·보고에 사용한 상세가 실제 retained ref 로 존재하고 충돌·부분실패·이전후보가 보존되면 종료.


### B4.5.L01 — 사례 A: 기존 J2 와 DP 의 같은 물리시험 비교

**분류 A · 단독 책임 T4(Data·Material·구성식 FE) · 상대 작업량 3/3**
원 연결: FN-08-02, FN-09-01, FN-09-02; SPEC-RESEARCH-003(FN03/04/06/07/09), EXPERIMENT-001, NUMERICAL-002.

**현재 구현 / 실제 잔여:** J2 CCX 와 DP/Neo-Hooke/Maxwell Hex8 FE 가 이미 있다. 이 leaf 는 DP 엔진 개발이 아니라 동일 시험·holdout·판단의 미완결 인수다.

**고정 지원 profile:** CCX-STATIC, LAW-FE, MATERIAL, POST

**사용자 입력 → 조작 → 출력·저장재개:** 동일 물리 geometry/BC/단축·압축·구속 이력, 법칙별 실제 계수 → point 및 FE 평가 → p–q·항복/소성체적·제하잔류·관측잔차 비교 → 독립 구속/압축 holdout → Study 판단·저장.

**수정 파일·서비스 / 재사용 경로:** caelab/law_native_fe.py; caelab/adapters/law_native_fe_worker.py; caelab/law_native_inspection.py; 기존 Material/Plan/Study·CCX J2 경로

**의존:** B4.2/L03; 비교는 같은 물리관측을 사용. mesh 차이는 B3.2.L03 또는 명시 ROI/측정 비교로 구분

**최소 확인 / 실패·취소 반례:** 한 geometry 의 세 시험(T/C/confinement)과 한 unload, 원 DPvariant·pressure sign·dilatancy/hardening 명시. FE 와 point 의 균질구간 값 대조. 서로다른 mesh 결과를 동일 IP 라고 표시하지 않음.

**종료조건:** 인장만맞춘 DP 를식별완료로하지않고 양모델 실제응답/holdout/판단과 coldread 가 완료. 공학불량허용치는 UNKNOWN 유지.


### B4.5.L02 — 사례 C 의 다영역 열·점탄성 FE 경로

**분류 D · 단독 책임 T4(Data·Material·구성식 FE) · 상대 작업량 3/3**
원 연결: FN-08-02, FN-09-01, FN-09-02; SPEC-RESEARCH-003(FN03/04/06/07/09), EXPERIMENT-001, NUMERICAL-002.

**현재 구현 / 실제 잔여:** 기존 FELUPE Hex8 세 법칙의 assembly/Newton/state 는 있다. 현재 affine/traction-free 단일 법칙 경로에서 실제 이중층의 자유 곡률·열 초기상태/관측시점까지가 잔여다.

**고정 지원 profile:** LAW-FE-THERMAL

**사용자 입력 → 조작 → 출력·저장재개:** 두 bulk 영역의 두께·CTE·Tref·탄성 또는 단일 branch Maxwell 를 명시 → 같은 T(t) 공급 → 자유곡률/구속상태 계산 → 온도복귀 후 두 지정 hold 시각의 곡률·계면인접응력·내부 state 선택 → 저장/재개.

**수정 파일·서비스 / 재사용 경로:** caelab/law_native_fe.py; caelab/adapters/law_native_fe_worker.py; [신규] caelab/law_native_thermal_regions.py; [신규] apps/research/law_thermal_conditions.py

**의존:** B6.3.L04 의 온도 port 계약, 기존 law_native(FELUPE)재사용; interface damage 는 B1.5.L02 별도

**최소 확인 / 실패·취소 반례:** 탄성 이중층 곡률독립기준과 작은 두 mesh, 같은 T/BC 복귀의 탄성잔류 0, Maxwell τ와 10τ 관측의 delayed recovery. 물성값은명시입력이며기본화금지; thermal mechanical strain/state 분해 검증.

**종료조건:** 같은유저문서의 multi-regionFE 에서실제 T→변형/상태가연결되고유한 hold 잔류를영구소성/손상으로오인하지않음. 세법칙재작성이나새 FEsolver 금지.


### B5.1.L01 — 혼합변수 DOE 의 실제 domain binding

**분류 A · 단독 책임 T5(Numerical·PDE·field 전달) · 상대 작업량 2/3**
원 연결: FN-20-01, FN-20-03; SPEC-NUMERICAL-001/002, CAD-NUMERICAL-001, RESEARCH-003.

**현재 구현 / 실제 잔여:** variable_domains·mixed DOE·종속식·범주·후보 상세가 있다. continuous rounding 을새로구현하지않는다.

**고정 지원 profile:** W, NUM

**사용자 입력 → 조작 → 출력·저장재개:** 기존 CAD/Material/PDE evaluator 선택 → continuous/integer/discrete/category·종속단위값 정의 → 실제 DOE → 행/응답/실패 선택 → 원 owner 검토·저장재개.

**수정 파일·서비스 / 재사용 경로:** caelab/variable_domains.py; caelab/numerical.py; caelab/numerical_extensions.py; 기존 RequestPlan/후보창

**의존:** 기존 domain binding; 새 physics 대기불필요

**최소 확인 / 실패·취소 반례:** 범주가실제 domain 설정을바꾸는한조합과종속변수, 금지조합/순환/실패후보. 연속 rounding 결과와구분; rank-deficient 설계안내. 실행예산·원 raw 결과고정.

**종료조건:** 실제 domain 입력과 typed 후보·선택·저장/채택참조가일치하면종료. 대수샘플의성공을모든 nativebinding 성공으로확대하지않음.


### B5.3.L01 — 일반 역해석의 고정 관측·feasible 후보 왕복

**분류 A · 단독 책임 T5(Numerical·PDE·field 전달) · 상대 작업량 2/3**
원 연결: FN-05-02, FN-21-01; SPEC-NUMERICAL-001/002, CAD-NUMERICAL-001, RESEARCH-003.

**현재 구현 / 실제 잔여:** 다시험 fit/잔차·mask/weights/holdout·DE 및실패/penalty 분리가있다. B4 의후보보존을복제하지않는다.

**고정 지원 profile:** NUM, MATERIAL

**사용자 입력 → 조작 → 출력·저장재개:** 동일위치·시각의복수관측과 bounds/objective/constraints/예산 → 실제평가 → feasible/failed/infeasible·raw/scaledresidual 분리 → 후보상세·명시채택/Study → 저장재개.

**수정 파일·서비스 / 재사용 경로:** caelab/numerical.py; caelab/numerical_document.py; caelab/numerical_fit_lineage.py; 기존 PlanUI

**의존:** B4.4.L01 의상세/채택계약

**최소 확인 / 실패·취소 반례:** 필수예측구간누락후보가낮은목적으로승격되지않음, holdout 미사용, penalty 표시분리. 반례한개와작은기존 fit. solver 전체 campaign 없음.

**종료조건:** 같은 mask/weight/scaledobjective 와 feasibility 를표·곡선·채택·보고가모두소비하며 coldread 실행 0 이면종료.


### B5.4.L01 — 필수 사례별 미분법 선택·기존 adjoint 인수

**분류 A · 단독 책임 T5(Numerical·PDE·field 전달) · 상대 작업량 2/3**
원 연결: FN-21-02; SPEC-NUMERICAL-001/002, CAD-NUMERICAL-001, RESEARCH-003.

**현재 구현 / 실제 잔여:** 기존 선형 adjoint·ordinary-residual FD·DE의 역할/지원 범위를 descriptor·Plan·원 결과에서 함께 읽는다. 실제 보존 S2의 두 방향 Taylor/원 허용값, FD의 h/h2·9회·holdout0, Picard의 DE/NOT_CONVERGED를 재사용해 선택·취소·저장·별도 cold를 확인했다. 현재 FD 간격에 따른 중앙/한쪽 비용 및 검증된 Jacobian 재사용0회, runtime 미확인 본문의 독립 검토 지적도 교정했다. [사용법과 실제 화면](NUMERICAL_DERIVATIVE_KO.md). 이 leaf에서 새 solver/fit/최적화를 반복하지 않았으며 범용 비선형 adjoint·공학 승인은 주장하지 않는다.

**고정 지원 profile:** NUM, DERIVATIVE

**사용자 입력 → 조작 → 출력·저장재개:** 선형 P1 의연속계수·목적/제약에는실제 adjoint 선택 → 독립방향검사 → 계산. 재료역해석의진단은기존 ordinary-residualFD, 형상·비선형·시간·연성최적화는명시 DE → 실패/미분불가·예산/원결과보존.

**수정 파일·서비스 / 재사용 경로:** caelab/linear_adjoint_contract.py; caelab/evaluation_adjoint.py; caelab/numerical_adjoint.py; caelab/experiment_final_diagnosis.py; apps/research/s2_gradient_widgets.py

**의존:** 기존 P1 evaluator 와 B7.4 의 FD 결과 계약

**최소 확인 / 실패·취소 반례:** 현재선형 P1 의두독립방향/Taylor 기준과 DE 필요상태하나, active-bound/미분불가/부족예산. FD/DE 를 adjoint 표시하지않음; 이전고정검사 tolerance 유지.

**종료조건:** 표 DERIVATIVE 가 GUI/descriptor/Plan 결과에동일하게노출되고기존선형 adjoint 와 FD/DE 가의미대로동작하면종료. 네범주범용 adjoint 는개발하지않음.


### B5.6.L01 — 보존 대리모델·다목적·Picard/MDO 한 정의

**분류 A · 단독 책임 T5(Numerical·PDE·field 전달) · 상대 작업량 3/3**
원 연결: FN-23-02, FN-24-01, FN-24-02; SPEC-NUMERICAL-001/002, CAD-NUMERICAL-001, RESEARCH-003.

**현재 구현 / 실제 잔여:** 국소 RBF 저장,3 개이상목적/Pareto 축,반복 Evaluation/공유변수가있다. B6.4 와같은구현소유자·한 leaf 로센다.

**고정 지원 profile:** NUM, EVALUATION

**사용자 입력 → 조작 → 출력·저장재개:** 저장대리모델또는반복 Evaluation 선택 → 변수/3 목적/제약/총예산 → 실제후보 → 전체차원 Pareto/선택모델근거 → 실제한점확인·명시채택 → 저장/재개.

**수정 파일·서비스 / 재사용 경로:** caelab/evaluation_definition.py; caelab/numerical.py; caelab/surrogate_archive.py; 기존 numerical_extensions/결과창

**의존:** 기존 MDO/연성 engine; 실제 field 예제는 B6.3 뒤 최종장면에서추가

**최소 확인 / 실패·취소 반례:** 두축투영이달라도전체 Pareto 불변, NOT_CONVERGED 목적사용금지, 후보마다 state 격리, prefix 재사용은정확입력만. 저장열람 fit/predict/solve0; 새예측/확인만명시실행.

**종료조건:** 동일 Evaluation 을직접/Plan 에서사용하며잔차·실패·budget·보존모델/후보참조가같고 coldread 가완료. B6.4 를별도재개발로중복세지않음.


### B6.1.L01 — 사용자 MFront→한 실제 FE interface

**분류 D · 단독 책임 T4(Data·Material·구성식 FE) · 상대 작업량 3/3**
원 연결: FN-08-01, FN-08-02, FN-09-01, FN-09-02; SPEC-RESEARCH-003(FN08/18/19), NUMERICAL-002.

**현재 구현 / 실제 잔여:** user_material/user_mfront 는 generic MGIS 재료점이며 FE export false. DP/Neo-Hooke/Maxwell FELUPE FE 를이공백과합쳐재작성하지않는다.

**고정 지원 profile:** MFRONT-FE

**사용자 입력 → 조작 → 출력·저장재개:** 명시승인된사용자 source·Tridimensional smallstrain behaviour/properties/state → 기존 TFELbuild·MGIS descriptor 검사 → 기존 FELUPE Hex8 assembly 의각 IP 에서동일 behaviour update/tangent → 하중/제하 FE → source/build/ABI·IPstate/실패·보존결과새 owner 읽기.

**수정 파일·서비스 / 재사용 경로:** caelab/user_material.py; caelab/adapters/user_mfront.py; caelab/adapters/user_mfront_worker.py; [신규] caelab/adapters/user_mfront_fe_worker.py; 기존 law_native_fe assembly 접점는 T4 만수정

**의존:** 기존 MGIS/TFEL runtime 와 source 승인. B4.5 와한소유자·한개수

**최소 확인 / 실패·취소 반례:** 사용자 linear law 와 history law 두 source,8Hex8 실제 freeinteriorDOF mesh. 한 IP 독립 MGIS 점 vsFE 균질응답, tangent FD, local/global 실패 trial state 복원. compile 성공≠FE 성공.

**종료조건:** generic smallstrain MGIS→FELUPE 하나의명시 pair 가실제 FE/원입력/저장재개까지지원되면종료. Code_Aster/CalculiX/Abaqus 모든 userinterface 를새필수로늘리지않음.


### B6.1.L02 — 구성식 increment·접선·FE IP 원값 인수

**분류 A · 단독 책임 T4(Data·Material·구성식 FE) · 상대 작업량 2/3**
원 연결: FN-08-01, FN-08-02, FN-09-01, FN-09-02; SPEC-RESEARCH-003(FN08/18/19), NUMERICAL-002.

**현재 구현 / 실제 잔여:** constitutive inspection 와 native law tangent/state 검사·FE/point 대조가있다. 패킷에서누락된 plugins/material_point 원문은실행호스트보존 source 로대조할것이며없다고법칙재개발하지않는다.

**고정 지원 profile:** MATERIAL, LAW-FE

**사용자 입력 → 조작 → 출력·저장재개:** 수락 increment·stress/strain/tangent measure 와 IP 선택 → 같은초기 state 의기존독립 perturbation 근거열기 → 원 protocol/FE 조건으로복귀 → 저장·coldread.

**수정 파일·서비스 / 재사용 경로:** caelab/constitutive_inspection.py; caelab/law_native_inspection.py; apps/research/constitutive_inspection_window.py; tests/law_native

**의존:** 기존세법칙; custom MFront 는 L01 완료때같은계약소비

**최소 확인 / 실패·취소 반례:** Neo-Hooke dP/dF,DP 지원 discrete tangent,Maxwell actualdt/state. nondifferentiable/failedstate 를접선 0 으로대체금지. 표/선택은무계산; 새 probe 만명시평가.

**종료조건:** 정의가같은접선 pair·원 state·units·IP 위치를 coldreader 가읽고명시새 probe 와단순조회가구분되면종료.


### B6.2.L01 — 독립 PDE 의 선언 모델별 입력·실제 해·재개

**분류 A · 단독 책임 T5(Numerical·PDE·field 전달) · 상대 작업량 3/3**
원 연결: FN-18-01, FN-18-02; SPEC-RESEARCH-003(FN08/18/19), NUMERICAL-002.

**현재 구현 / 실제 잔여:** Windows dimensioned ODE,scikit-fem P1/열탄성과기존 Linux nonlinear/transient/vector/imported adapters 가있다. WindowsPDEengine 부재라고되돌리지않는다.

**고정 지원 profile:** W, PDE

**사용자 입력 → 조작 → 출력·저장재개:** CAD 없이 ODE 또는지원 weakform/공간모델선택 → 식/space/영역/BC/IC·계수·단위편집 → Check 후명시 Run → 실제해/잔차/동일 norm 기준 → Post/저장·재개. 미지원 AST 는초안보존.

**수정 파일·서비스 / 재사용 경로:** caelab/dimensioned_expression.py; caelab/dimensioned_models.py; caelab/scikit_fem_models.py; caelab/adapters/dimensioned_ode.py; caelab/adapters/dimensioned_weak.py; apps/research/pde_window.py

**의존:** 기존 runtime 만; PDE 편집/보존조회는 Linux 설치불필요

**최소 확인 / 실패·취소 반례:** Windows ODE 한개와 P1 열/열탄성제조해, Linux 기존 adapter 별작은원 reference 근거연결. 다른 norm 비교·Tref 중복·차원오류·취소 lastacceptedstate 확인. 새전체 campaign 없음.

**종료조건:** 표 PDE 의실제 declaredbackend·OS·식범위가편집/실행/오류/재열기와일치하면종료. COMSOL 모든 PDE 를지원한다고표시하지않음.


### B6.3.L01 — 변위 vector → 구조 Dirichlet port

**분류 D · 단독 책임 T5(Numerical·PDE·field 전달) · 상대 작업량 3/3**
원 연결: FN-19-02; SPEC-RESEARCH-003(FN08/18/19), NUMERICAL-002.

**현재 구현 / 실제 잔여:** Post vector 기저변환은있지만 receiver solver vector/tensor port 는 unsupported. 새 mapper 를복제하지않고 B3 의 shape mapping 을소비한다.

**고정 지원 profile:** TR-U

**사용자 입력 → 조작 → 출력·저장재개:** 보존 CCX U field+reference geometry+actualtime → 목표 C3D10 경계 set/좌표계·단위선택 → 원값/수신 prescribedU 와 maskpreview → 실제수신구조해석 → 연결정의/결과저장.

**수정 파일·서비스 / 재사용 경로:** [신규] caelab/structural_field_ports.py; [신규] caelab/structural_field_transfer.py; caelab/evaluation_definition.py 는 root; receiver condition writer 는 T1 소유 hunk

**의존:** B3.2.L03 의 shape mapping; B1.4.L02 의조건계약

**최소 확인 / 실패·취소 반례:** rigid translation/rotation 의소변형 u 와 affine displacement 전달, differentmesh 공통경계. essentialreceiver 점누락이면 Run 차단. 길이단위변환과 frame 회전 1회.

**종료조건:** 정확한 U→prescribedU 한 port 를 native 수신계산까지완료. 전송 metadata 만갖고끝내지않으며보존성주장없음.


### B6.3.L02 — 초기 응력 tensor port

**분류 D · 단독 책임 T5(Numerical·PDE·field 전달) · 상대 작업량 3/3**
원 연결: FN-19-02; SPEC-RESEARCH-003(FN08/18/19), NUMERICAL-002.

**현재 구현 / 실제 잔여:** 보존 S tensor 를 Post 에서읽는기능과 solver 초기상태소비는별개다. 무한한 tensor 종류를추가하지않고한 port 로고정한다.

**고정 지원 profile:** TR-S

**사용자 입력 → 조작 → 출력·저장재개:** 선형탄성 CCX C3D10 의전체 6 성분원 IP 응력/원 mesh·frame → 같은 mesh 의명시초기 stress 상태 → RσRᵀ/단위확인 → 작은후속 static 증분 → 초기/후속응력·평형/원 lineage 저장.

**수정 파일·서비스 / 재사용 경로:** caelab/structural_field_ports.py [L01 단독작성자]; [신규] caelab/stress_state_transfer.py; initial_field_conditions/receiver 는 T1 소유 hunk

**의존:** B1.4.L02; B3.2 의 tensorbasis 계약; mapper 가필요없는 exactsame-IP 로첫인도

**최소 확인 / 실패·취소 반례:** 정확 nativeIP ID/ordering·printedprecision 과 6 성분회전, 초기 equilibrium. 누락성분·다른 mesh·σ만있는소성 state 재개거절. 전달후명시하중증분의탄성응답대조.

**종료조건:** 같은 mesh·선형탄성초기응력 port 의실제수신 native 상태와 coldread 완료. 응력만으로 damage/plastic restart 를인증하지않음.


### B6.3.L03 — CCX 고정 지지 RF 에서 다른 C3D10 경계로 보존 하중 전달

**분류 D · 단독 책임 T5(Numerical·PDE·field 전달) · 상대 작업량 3/3**
원 연결: FN-19-02; SPEC-RESEARCH-003(FN08/18/19), NUMERICAL-002.

**현재 구현 / 실제 잔여:** CCX 2.22 RF/FORC output 과 reader 를 재사용한다. 접촉쌍 힘 생산이나 임의 nodal-force 분배는 목표가 아니다. 선택한 지지경계 native 반력에서 `f_source = -R_source`, 수신에는 `f_target = Hᵀf_source`로 전달하는 제품 연결·인수가 남았다.

**고정 지원 profile:** TR-F — Windows CCX 2.22, 선형 탄성 C3D10, 작은 변형·수렴한 정적 state, global XYZ SPC-only 지지경계, 다른 C3D10 경계의 6 절점 TRI6 quadratic H. 첫 범위는 일반 MPC 가 없는 모델이다.

**사용자 입력 → 조작 → 출력·저장재개:** frozen source deck 의 고정 node ID 와 receiver face 선택 → 실제 deck preflight 에서 각 source DOF 의 고정, 선택 node CLOAD 부재(다른 위치 CLOAD 는 허용), 그 node 에 연결된 모든 element 의 DLOAD/body load 부재, MPC/TRANSFORM/contact/rigid coupling 부재 확인 → 명시 `*NODE FILE,GLOBAL=YES`의 `RF`에서 native FRD `FORC` 세 성분을 N·global XYZ·원좌표·step/increment/static load parameter 와 mask 로 읽기 → 명시 action/reaction 부호로 `f_source=-R_source` 기록 → `Hᵀ`를 다른 C3D10 경계에 적용 → 원·수신 하중/결과를 저장·cold reopen 한다.

**수정 파일·서비스 / 재사용 경로:** `contact_deck.py`의 RF 출력, `adapters/frozen_fem.py`의 node/coverage 검사, `contact_results.py`의 FORC 경로, 기존 shape mapper. Evaluation gate 와 공통 provenance 는 root 가 통합한다. RF 원값과 derived load 는 분리해 보존한다.

**의존:** B3.2.L03 의 quadratic H 기하 계약만 공유한다. B1.6 contact-pair producer 는 선행조건이 아니다. 일반 contact-pair nodal-force capability 는 별도 미입증으로 둔다.

**최소 확인 / 실패·취소 반례:** 실제 deck 에서 선택 node 의 CLOAD 와 인접 element DLOAD/body load 부재를 확인한다. 선택 source node CLOAD, 인접 DLOAD/body load, MPC/TRANSFORM/contact/tie/rigid coupling, 누락·중복 node, 중복 face, coverage 부족이면 downstream solve 를 제출하지 않는다. 단위·ID·좌표·시각을 보존하고 합력/기준점 모멘트/가상일을 대조한다. H partition/affine 재현 1e-10 및 receiver 평형 1e-6 을 유지한다. force 를 임의 node 로 나누거나 pressure 로 바꾸지 않는다.

**종료조건:** 유한 source→RF/FORC→부호변환→다른 C3D10 의 Hᵀ load→보존량·cold reopen 까지 닫는다. 접촉쌍 분해와 범용 mapper 는 범위 밖이다.

### B6.3.L04 — 기존 P1 온도에서 3D 이중층·계면까지

**분류 D · 단독 책임 T5(Numerical·PDE·field 전달) · 상대 작업량 3/3**
원 연결: FN-19-02; SPEC-RESEARCH-003(FN08/18/19), NUMERICAL-002.

**현재 구현 / 실제 잔여:** 다른 mesh/time P1 온도→2D 열탄성은실제 Windows 경로가있다. 원사례 C 의 3D 층/계면수신까지연결하는것만잔여다.

**고정 지원 profile:** TR-T3D

**사용자 입력 → 조작 → 출력·저장재개:** 기존 P1 T(x,y,t_i)결과 → 명시 extrusion 단면·3D receiver 좌표·실제시각선택 → K/ΔT·구조 Tref 검토 → FELUPE bonded thermal/Maxwell variant 와 별도로 같은 Evaluation 의 Aster HEXA8/CZM_LIN_REG 계면수신 → 곡률/traction/damage/reclosure/hold 시각결과 → Evaluation 저장.

**수정 파일·서비스 / 재사용 경로:** [신규] caelab/temperature_receiver_3d.py; 기존 transfer_inspection/physical_fields·P1 mapping; receiver 는 T4 FELUPE bonded thermal/Maxwell variant 와 T2 Aster HEXA8/CZM_LIN_REG 계면 경로로 분리한다

**의존:** B4.5.L02 thermalFE, B1.5.L02 implicitinterface. 기존 P1 온도 producer 는즉시사용

**최소 확인 / 실패·취소 반례:** 두 P1mesh·두실제온도 snapshot 과 3D 두층모델. 상수/선형 T 와 extrusion 방향불변검사, receiver 필수점 missing 차단. 같은 T→곡률기준, Tref1회, 실제 interface 응답연결.

**종료조건:** 온도 producer 와 3Dbulk/interface consumer 를하나의 Evaluation 에서실제로이어계산·coldread. 두독립데모를연성성공으로합치지않음.


### B7.1.L01 — 문헌 원문·독립 Study·판단 보존

**분류 A · 단독 책임 T6(Study·Expert·실험·Report) · 상대 작업량 2/3**
원 연결: FN-29-01, FN-29-02, FN-29-03; SPEC-EXPERIMENT-001, EXPERT-001/002, DESKTOP-002.

**현재 구현 / 실제 잔여:** 문헌 exactknowledge/보존 locator/Study owner 와교환·portable 연결이있다. 원문 URL 만붙이는새후속조사가아니다.

**고정 지원 profile:** W, RESEARCH

**사용자 입력 → 조작 → 출력·저장재개:** 로컬문헌/표·그림 locator 선택 → 독립 Study 질문/가설·경쟁증거 작성 → 원문확인/판단명시 → 새증거 추가해도옛판단보존 → 저장·외부 provider 없이재열기.

**수정 파일·서비스 / 재사용 경로:** 기존 literature/source owner; caelab/study_document.py; apps/research/study_window.py; portable knowledge helpers

**의존:** 기존 exact assets/locator; AI 불필요

**최소 확인 / 실패·취소 반례:** 원파일이동·내용변경·누락·locator 범위오류, 반론과 UNKNOWN 보존. 원자료읽기권한/보존범위 밖의전체문서가있다고표시금지. 새 provider 호출없이 cold.

**종료조건:** 문헌구간·결과·판단의정확 ref 를읽고수리/새 branch·저장재개가완료면종료.


### B7.2.L01 — 기존 3 역할 Expert 의 중단·한도·부분응답 재개

**분류 A · 단독 책임 T6(Study·Expert·실험·Report) · 상대 작업량 2/3**
원 연결: FN-30-01, FN-30-02; SPEC-EXPERIMENT-001, EXPERT-001/002, DESKTOP-002.

**현재 구현 / 실제 잔여:** 실제 3 역할초기조사·상호질문/답변·지도·보고서성공은유지한다. 고정답변으로새증거를만들지않는다.

**고정 지원 profile:** W, EXPERT

**사용자 입력 → 조작 → 출력·저장재개:** 기존 Expert 문서·실제 3 역할/provider 선택 → 질문/개입·pause/resume → 한도/연결실패후수락된발언·reply 대상/원문보존 → 명시후속 Plan 검토 → 저장/재개.

**수정 파일·서비스 / 재사용 경로:** caelab/assist 기존 costorm 관련모듈; apps/research/expert_window.py; 기존 ExpertDocuments/후속 result-return

**의존:** 기존승인구독 provider 만; 다른팀계산/편집은무 provider 독립

**최소 확인 / 실패·취소 반례:** 기존실제대화기록을읽기재개, failure/partial/limit 대역은대역표시. 필요한최종 live 인수 1 회만기존 provider. 중복발언/새 Plan 자동생성·fallback0.

**종료조건:** 실제발언과원문/계획제안이정확보존되고중단/한도/명시재개가사용자 UI 에서동작. provider 없으면초안/보존조회가가능하며무료위장 fallback 없음.


### B7.3.L01 — B−A 비교 불확실성

**분류 D · 단독 책임 T6(Study·Expert·실험·Report) · 상대 작업량 3/3**
원 연결: FN-05-01; SPEC-EXPERIMENT-001, EXPERT-001/002, DESKTOP-002.

**현재 구현 / 실제 잔여:** `e76cde6`에서 supplied covariance 를 쓰는 fixed-coordinate scalar B−A 차이 전파, 저장 비교, Plan/Study 와 cold read 가 통합됐다. 남은 것은 기존 교정·측도·고정 gauge·시간정렬 chain 의 유한 1차 민감도 연결이다. 게시된 선형 slice 를 재개발하지 않으며 full 3D F/J 불확실 전파나 신규 Monte Carlo 엔진도 만들지 않는다.

**고정 지원 profile:** W, UNCERTAINTY

**남은 유한 변환 chain:** 기존 affine 교정 `y=a(x−x0)+b`와 정확 단위 → 고정 방향 `n`의 `g=n·(uB−uA)`, `e=g/L0`, `lambda=1+e`, `logstrain=ln(lambda)` → `P=force/A0`, 단축·동축 protocol 에서 `sigma=P*lambda/J` → 기존 piecewise-linear 정렬에서 operand 별 한 공통 시간 offset `delta_t`의 `y(t+delta_t)`와 같은 구간 slope. 실제 저장 chain 의 시간정렬·물리변환 순서를 따른다.

**입력과 범위:** 원 raw source identity, 원값, a/b/x0/L0/A0/J/delta_t 의 identity, 실제 공유·교차 covariance 를 보존한다. L0/A0/J 는 제공된 양수만 허용하고 lambda>0 이어야 한다. `J=1`은 명시 가정일 때만 쓴다. x0 를 b 에 흡수하거나 교정을 중복하지 않는다. 고정 n·원 기준 좌표/기저·target time grid 전제다. uncertain orientation, 임의 full 3D F, 개별 표본 확률시각은 추가하지 않는다. 미제공 covariance 를 독립/0 으로 채우지 않는다.

**미분·실패 정책:** 기존 PSD, `JΣJᵀ`, Plan/Study/보존 reader 를 소비한다. analytic Jacobian 과 필요한 h/h2 대조를 한다. time offset 평가점의 knot, gap, 범위 밖, 미분 비유일은 해당 불확실성을 UNKNOWN 으로 남기고 원값·원행을 보존한다. 시간·물리량 변환 순서는 저장된 실제 관측 chain 과 동일하다.

**종료조건:** 원 covariance·identity, 관측 순서·단위·평가점·Jacobian·UNKNOWN 이 Plan/Study 와 cold reopen 에서 같은 값이면 종료한다. 범용 비선형 확률엔진·Monte Carlo 는 범위 밖이다.

### B7.4.L01 — 기존 robust/DE 최종 perturbation→다음 시험

**분류 A · 단독 책임 T6(Study·Expert·실험·Report) · 상대 작업량 2/3**
원 연결: FN-05-02; SPEC-EXPERIMENT-001, EXPERT-001/002, DESKTOP-002.

**현재 구현 / 실제 잔여:** experiment_final_diagnosis 가 bounds/예산내원후보재평가·ordinary residual FD·h/h2/좌우검사·국소 SVD·보존 reader 를이미구현한다. identification.py 의 linear-only 만보고전체미구현으로판정하면오류다.

**고정 지원 profile:** NUM, IDENTIFICATION

**사용자 입력 → 조작 → 출력·저장재개:** 보존 robust-loss 또는 DE 최종후보 → 명시추가예산/FD step·bounds 고정 → 기존재평가 → scaledSVD/약식별방향·one-sided/실패 표시 → 기존 Study 에서그방향을구별하는다음시험/고정계수판단 → 저장재개.

**수정 파일·서비스 / 재사용 경로:** caelab/experiment_final_diagnosis.py; caelab/experiment_analysis_service.py; caelab/experiment_analysis_actions.py; caelab/experiment_analysis_reporting.py; 기존 analysis/Study UI

**의존:** B5.3.L01 의정확원후보/관측; 새로운 optimizer/전파엔진불필요

**최소 확인 / 실패·취소 반례:** robust 와 DE 각한후보, bound 근처한방향·차분실패·예산소진·원 residual 재현불일치. FD 가수정되지않은잔차미분임을확인; 전역유일성·통계 CI 로승격금지.

**종료조건:** 명세가허용하는 bounded perturbation 진단과후속시험기록이실제연결되면종료. profile-likelihood 전구간탐색을추가필수로만들지않음.


### B7.5.L01 — 실제 3D 장면·판단·수치가 들어간 한 보고서

**분류 A · 단독 책임 T6(Study·Expert·실험·Report) · 상대 작업량 2/3**
원 연결: FN-32-01; SPEC-EXPERIMENT-001, EXPERT-001/002, DESKTOP-002.

**현재 구현 / 실제 잔여:** Post native capture·retained image assets·Report/Study/문헌연결은있다. 원 source 반환구현은 B3.4 가단독소유한다.

**고정 지원 profile:** W, POST, RESEARCH

**사용자 입력 → 조작 → 출력·저장재개:** 같은 result/frame/field/display 조건의 native scene 캡처 → Study 본문·표/곡선·문헌 locator 와같은보고서편집 → 원그림/값검토 → 내보내기 → source 폴더없이다시열기.

**수정 파일·서비스 / 재사용 경로:** 기존 report owner/export/scene-capture helper; apps/research/report_window.py; apps/desktop_post/workspace.py export 는 root

**의존:** B3.4.L01 의원선택반환; 기존그림으로병렬인수

**최소 확인 / 실패·취소 반례:** 실제 native 한 scene 와실패/UNKNOWN 한결과를같은 Report 에넣음. frame/색범위/변형배율변경은명시새 capture; 옛그림불변, watermark 가아닌원 asset 일치. 저장쓰기실패/부분내보내기보존.

**종료조건:** 보고서에서실제숫자/장면조건·원근거를검토하고같은본문/그림으로 cold/re-export 가능. 이미지를 3D 상호작용뷰라부르지않음.


### B7.6.L01 — 장비 없이 닫는 공통 취득·sequence·종료 소프트웨어

**분류 D · 단독 책임 T6(Study·Expert·실험·Report) · 상대 작업량 3/3**
원 연결: FN-35-01; SPEC-EXPERIMENT-001, EXPERT-001/002, DESKTOP-002.

**현재 구현 / 실제 잔여:** 기록 CSV 재생의 sequence·공통 상태·중지 응답·원문/교정 보존·부분 Data·저장본 재개 소프트웨어를 통합했다. 문서 전환과 동시 저장 오류도 수정했다. 실제 장비와 물리적 중지 응답은 별도 L02이며, OS 직접 조작의 현재 판정은 CURRENT_STATE를 따른다.

**고정 지원 profile:** W, ACQUISITION

**사용자 입력 → 조작 → 출력·저장재개:** 취득계획·채널/단위·clock 선언 → 파일 replay/공통 adapter 로 sample 받기 → sequence/gap/원 bytes 보존 → pause/stop 요청·실제 receipt 표시 → 부분 Data 검토·교정연결 → 저장·명시 resume.

**수정 파일·서비스 / 재사용 경로:** [신규] caelab/acquisition_session.py; [신규] caelab/adapters/acquisition_replay.py; [신규] apps/research/acquisition_panel.py; 기존 Data/experiment_calibration·JobManager 재사용

**의존:** 기존 Data owner/수집 metadata; 장비/host/provider 불필요

**최소 확인 / 실패·취소 반례:** 순서뒤바뀜·중복동일 bytes/충돌 bytes·gap·센서 clockreset·연결끊김·stop 무응답·쓰기실패. replay EOF/프로세스종료를장비물리 stopACK 로표시금지. acknowledged prefix/cold/resume 중복 0.

**종료조건:** 공통 adapter 계약과실제작동하는 replay/오류·중지·부분저장 UI 가완료되면소프트웨어 leaf 닫음. 실장비 leaf 는별도로열어둠.


### B7.6.L02 — 실제 장비 한 종류의 binding·권한·물리 stop 인수

**분류 E · 단독 책임 T6(Study·Expert·실험·Report) · 상대 작업량 2/3**
원 연결: FN-35-01; SPEC-EXPERIMENT-001, EXPERT-001/002, DESKTOP-002.

**현재 구현 / 실제 잔여:** 장비모델·프로토콜·채널/교정서·접속권한과물리 stop 시험조건이제공되지않았다. 소프트웨어개발면제가아니라장비별명시 binding 과물리인수의외부조건이다.

**고정 지원 profile:** ACQUISITION-DEVICE

**사용자 입력 → 조작 → 출력·저장재개:** 제공된한장비/펌웨어/프로토콜과채널을 L01 에 binding → 실제 sample/단위/clock·sequence 확인 → 허용시험의 stoprequest/장비 ACK·실제상태확인 → 원자료·교정·receipt 저장.

**수정 파일·서비스 / 재사용 경로:** 장비별 driver(모델제공전파일명/명령발명금지); L01 공통경계

**의존:** B7.6.L01 + 실제장비/승인권한/프로토콜/중지조건

**최소 확인 / 실패·취소 반례:** 실측단위·시각·누락/gap 와안전하게승인된물리 stop1회. simulator 성공을실장비로세지않고장비 ACK/실제중지구별.

**종료조건:** 해당장비의정확 runtime/protocol 과실측·stop 증거가남아야종료. 외부조건없으면 NOT_RUN_EXTERNAL; 전체 hardware 완료라고표시불가.


### B8.1.L01 — 모든 독립 앱·파일의 정확 owner 열기

**분류 A · 단독 책임 T7(독립 실행·연결·이동사본·Windows 배포) · 상대 작업량 2/3**
원 연결: FN-01-01, FN-33-01; SPEC-DESKTOP-001/002, NUMERICAL-002(외부교환).

**현재 구현 / 실제 잔여:** 기존 launcher/desktop_links/owner 등록·동일문서활성화는있다. 임의 active doc 추정또는새 windowframework 개발은없다.

**고정 지원 profile:** W, DOCS

**사용자 입력 → 조작 → 출력·저장재개:** 표 DOCS 의각문서/외부 Post 파일에서직접열기 → 같은 store/doc 는기존 owner 활성화, 다른 store 동명이문서는분리 → 결과읽기 → 닫기/새 process 재개.

**수정 파일·서비스 / 재사용 경로:** caelab/desktop_links.py; apps/research/desktop.py; 기존 desktop_documents/open_registry/launcher

**의존:** 없음; 필요한도구만설치

**최소 확인 / 실패·취소 반례:** 같은 doc 중복열기·다른 store/id·owner 종료뒤재열기·잘못된 receipt·없는 target. 선택한 store/session 만변경, 결과열기 solver/provider0.

**종료조건:** 명시문서유형의직접진입·owner 재사용·저장재개가실제 Windows 에서동작. Workbench/AI/CAD 를연구앱필수로요구하지않음.


### B8.2.L01 — 여러 owner 의 편집·부분저장·복구초안

**분류 A · 단독 책임 T7(독립 실행·연결·이동사본·Windows 배포) · 상대 작업량 3/3**
원 연결: FN-02-01, FN-02-02, FN-02-03, FN-07-01; SPEC-DESKTOP-001/002, NUMERICAL-002(외부교환).

**현재 구현 / 실제 잔여:** 관련저장/유실응답/복구 capsule·adoption CAS 코드가있다. 한 Material 저장성공을복수문서저장완료로표시하지않는다.

**고정 지원 profile:** W, DOCS

**사용자 입력 → 조작 → 출력·저장재개:** Data/Material/Plan 두 owner 에서미확정셀입력·paste/초점전환 → 관련저장 → 한 owner 실패 → 성공 receipt 유지/실패 owner 만재시도 또는복구초안남기고닫기 → 새 process 복원.

**수정 파일·서비스 / 재사용 경로:** 기존 related_documents/related_save/recovery_capsule; apps/research 관련저장 dialog; 공통 owner/Workbench 는 Codex 단독

**의존:** 기존 portableassets 와 atomicrevision; B4.4 채택/상세와 receipt 계약

**최소 확인 / 실패·취소 반례:** Enter/Esc/Undo 가정확 owner 에만적용, 부분 diskfail/ACKlost/staleCAS, capsule 쓰기실패시창닫힘차단, 원문미확정셀보존. 성공문서를다시저장하지않음.

**종료조건:** 각 owner 의 buffer/draft/savedrevision/receipt 가정확하고 cold 복구·실패 owner 재시도까지동작. silentrollback/전체성공표시 0.


### B8.3.L01 — 이동 사본 전체 선언 문서의 cold 편집

**분류 A · 단독 책임 T7(독립 실행·연결·이동사본·Windows 배포) · 상대 작업량 3/3**
원 연결: FN-01-02; SPEC-DESKTOP-001/002, NUMERICAL-002(외부교환).

**현재 구현 / 실제 잔여:** portable project/connection/retained input·현재 ack·exactknowledge 가이미있다. C01/C02/C03 잔여를원소스대조없이새 store 로다시만들지않는다.

**고정 지원 profile:** W, DOCS

**사용자 입력 → 조작 → 출력·저장재개:** 표 DOCS 의저장문서/원자료/선택결과를기존이동사본으로보관 → 원 store 와 provider 환경차단 → 새경로/새 process 에서열기·현재초안편집/저장 → 다시복사·재열기.

**수정 파일·서비스 / 재사용 경로:** caelab/portable_project.py; caelab/portable_project.py [정확존재파일확인]; 기존 portable_*·각 owner retained_inputs

**의존:** 각문서의기존보존자료; B6.1 실행 runtime 는읽기에필수아님

**최소 확인 / 실패·취소 반례:** 한글/공백경로, 저장후 ack 된추가입력·부분 save receipt·원문헌 raw source·FCStd/Post dependency. 임의 latest 대체·외부 store 조회 0; 원본불변.

**종료조건:** 선언한모든문서종류의읽기/편집/재저장이원 store 없이지속되고지원표와실제 assets 가같으면종료. 필요한 native 실행 runtime 까지복사됐다고주장하지않음.


### B8.4.L01 — 외부 batch·remote 공통 소프트웨어 계약 인수

**분류 A · 단독 책임 T2(접촉·비선형·동해석·충격·Runner) · 상대 작업량 2/3**
원 연결: FN-25-01, FN-26-01, FN-26-02; SPEC-DESKTOP-001/002, NUMERICAL-002(외부교환).

**현재 구현 / 실제 잔여:** SSH/Slurm/PBS transport·submit token/poll/cancel/retrieve 본코드와 tests 가있다. 실제 host 미제공은 L02–L04 로분리.

**고정 지원 profile:** W, REMOTE

**사용자 입력 → 조작 → 출력·저장재개:** 파일교환평가기/remote 계획·inputmanifest 선택 → 제출확인·상태읽기 → 유실응답재확인·취소 → 원출력 checksum 회수 → partial/failed 보존·coldresume. localtransport/replayedprotocol 은대역표기.

**수정 파일·서비스 / 재사용 경로:** caelab/remote_execution.py; caelab/remote_schedulers.py; caelab/remote_transport.py; apps/research/remote_execution_dialog.py; 기존 file-exchange

**의존:** 기존 JobManager; 실제 host 없이 protocol tests·UI 부터종료가능

**최소 확인 / 실패·취소 반례:** 같은 token 의 submit 응답유실·연결끊김·scheduler accounting 없음·출력손상·stalebatch/duplicate. 같은 ID 재확인으로중복 submit0; unknowntermination 자동 kill/retry0.

**종료조건:** 고정지원명령/상태 grammar 에대해오류/재개·UI/원결과가완결. 실 host 성공으로표시하지않으며새스케줄러/서버개발없음.


### B8.4.L02 — SSH 직접 실행 실제 승인 호스트 인수

**분류 E · 단독 책임 T2(접촉·비선형·동해석·충격·Runner) · 상대 작업량 2/3**
원 연결: FN-25-01, FN-26-01, FN-26-02; SPEC-DESKTOP-001/002, NUMERICAL-002(외부교환).

**현재 구현 / 실제 잔여:** 연결/상태/취소/회수코드는있으나승인 host·계정·queue/자원·solver 설치및접근권한이첨부에없다. 실제버전은그 host 에서기록해야한다.

**고정 지원 profile:** REMOTE

**사용자 입력 → 조작 → 출력·저장재개:** SSH 직접 실행의한승인 host 에서작은기존 job 제출 → 실제 jobID/수행상태 → 연결복구·취소확인 → manifest 에일치하는원출력회수 → 새 process 동일 remotejob 재확인.

**수정 파일·서비스 / 재사용 경로:** 기존 remote_execution/remote_schedulers·설정문서(새 server/유료서비스없음)

**의존:** B8.4.L01 + 해당 host/권한/실행 runtime

**최소 확인 / 실패·취소 반례:** 정상한 job 와취소한 job, 연결복구중복 submit0, PID 또는 accounting 의실제종료·checksum, ownedjob 만정리.

**종료조건:** 선정 host 의실제 version/protocol/job/원출력·취소를확인할때만해당 leaf 종료. host 없음은 NOT_RUN_EXTERNAL.


### B8.4.L03 — Slurm 실제 승인 호스트 인수

**분류 E · 단독 책임 T2(접촉·비선형·동해석·충격·Runner) · 상대 작업량 2/3**
원 연결: FN-25-01, FN-26-01, FN-26-02; SPEC-DESKTOP-001/002, NUMERICAL-002(외부교환).

**현재 구현 / 실제 잔여:** 연결/상태/취소/회수코드는있으나승인 host·계정·queue/자원·solver 설치및접근권한이첨부에없다. 실제버전은그 host 에서기록해야한다.

**고정 지원 profile:** REMOTE

**사용자 입력 → 조작 → 출력·저장재개:** Slurm 의한승인 host 에서작은기존 job 제출 → 실제 jobID/수행상태 → 연결복구·취소확인 → manifest 에일치하는원출력회수 → 새 process 동일 remotejob 재확인.

**수정 파일·서비스 / 재사용 경로:** 기존 remote_execution/remote_schedulers·설정문서(새 server/유료서비스없음)

**의존:** B8.4.L01 + 해당 host/권한/queue/회계조회권한/실행 runtime

**최소 확인 / 실패·취소 반례:** 정상한 job 와취소한 job, 연결복구중복 submit0, PID 또는 accounting 의실제종료·checksum, ownedjob 만정리.

**종료조건:** 선정 host 의실제 version/protocol/job/원출력·취소를확인할때만해당 leaf 종료. host 없음은 NOT_RUN_EXTERNAL.


### B8.4.L04 — OpenPBS 실제 승인 호스트 인수

**분류 E · 단독 책임 T2(접촉·비선형·동해석·충격·Runner) · 상대 작업량 2/3**
원 연결: FN-25-01, FN-26-01, FN-26-02; SPEC-DESKTOP-001/002, NUMERICAL-002(외부교환).

**현재 구현 / 실제 잔여:** 연결/상태/취소/회수코드는있으나승인 host·계정·queue/자원·solver 설치및접근권한이첨부에없다. 실제버전은그 host 에서기록해야한다.

**고정 지원 profile:** REMOTE

**사용자 입력 → 조작 → 출력·저장재개:** OpenPBS 의한승인 host 에서작은기존 job 제출 → 실제 jobID/수행상태 → 연결복구·취소확인 → manifest 에일치하는원출력회수 → 새 process 동일 remotejob 재확인.

**수정 파일·서비스 / 재사용 경로:** 기존 remote_execution/remote_schedulers·설정문서(새 server/유료서비스없음)

**의존:** B8.4.L01 + 해당 host/권한/queue/회계조회권한/실행 runtime

**최소 확인 / 실패·취소 반례:** 정상한 job 와취소한 job, 연결복구중복 submit0, PID 또는 accounting 의실제종료·checksum, ownedjob 만정리.

**종료조건:** 선정 host 의실제 version/protocol/job/원출력·취소를확인할때만해당 leaf 종료. host 없음은 NOT_RUN_EXTERNAL.


### B8.5.L01 — 연결 graph/list·관계 수정의 실제 GUI 왕복

**분류 A · 단독 책임 T7(독립 실행·연결·이동사본·Windows 배포) · 상대 작업량 2/3**
원 연결: FN-31-01; SPEC-DESKTOP-001/002, NUMERICAL-002(외부교환).

**현재 구현 / 실제 잔여:** graph·drag/list·관계추가/수리/해제·owner 열기코드가있다. 새노드 canvas 를개발하지않는다.

**고정 지원 profile:** W, DOCS

**사용자 입력 → 조작 → 출력·저장재개:** 기존관련문서를 graph 또는 list 에서선택 → menu/drag 동일연결미리보기 → Apply/Cancel → 정확 owner 열기 → brokenref 수리 또는새 revision 제안 → 저장/재개.

**수정 파일·서비스 / 재사용 경로:** 기존 apps/research 연결 graph/list UI; caelab/desktop_links.py; 관계명령 dispatcher 는 root

**의존:** B8.1/L02 의 owner/저장

**최소 확인 / 실패·취소 반례:** drag/menu 동등, 잘못된 port·다른 store·stalegeneration·중도 cancel, broken 과 newrev 별도. source 원본편집 0·빈 placeholder 로성공표시 0.

**종료조건:** 1440×900 과좁은창에서노드/포트/연결의선택·키보드대안·저장재개가완료되면종료.


### B8.6.L01 — 새 Windows PC 설치·native 발견·소스/라이선스 폐쇄

**분류 A · 단독 책임 T7(독립 실행·연결·이동사본·Windows 배포) · 상대 작업량 3/3**
원 연결: FN-33-01, FN-33-02, FN-34-01; SPEC-DESKTOP-001/002, NUMERICAL-002(외부교환).

**현재 구현 / 실제 잔여:** ZIP 고정 upstream 준비와 FreeCAD/PV 발견선택은게시됐다. 이 ZIP 에는 scripts/pyproject/runtime binaries/SDK source 및일부 plugin Python 이없으므로기록된구현을재작성하지말고배포원문/의존폐쇄를검증한다.

**고정 지원 profile:** W, PRE, POST, LAW-FE, PDE

**사용자 입력 → 조작 → 출력·저장재개:** Windows 비 WSL 새사용자환경에서공개소스/설치 manifest 준비 → 기존 native 설치발견·명시선택 → 독립앱/CCX/OpenCourant/WindowsPDE·Material 실행 → 저장·재시작 → 설치오류수정. 기존앱/사용자설정불변.

**수정 파일·서비스 / 재사용 경로:** 기존 scripts/prepare_fixture_upstream.py·Windows launcher/installer·pyproject/lock/native SDK packaging(패킷밖); caelab/adapters/native_doctor.py; tests/test_windows_upstream_source.py

**의존:** 각완료된 runtime profile 만독립배포; SDK 와 CCX 관측확장은그기능설치에만의존

**최소 확인 / 실패·취소 반례:** 한글/공백경로·DLL/권한·잘못된 runtime·누락 plugin source·offline retained read. 공개 trackedsource 와실행에필요한모듈/라이선스/redistribution 조건을 exactmanifest 로대조. 설치/수치/공학승인분리.

**종료조건:** 새 PC 에서지원기능이실제사용가능하고원문/빌드/버전/무료의존·라이선스목록과한국어예제가일치. 설치미확인을외부조건으로밀어내지않음.


### B8.6.L02 — GUI/CLI/Python/MCP 동일 명령·owner

**분류 A · 단독 책임 T7(독립 실행·연결·이동사본·Windows 배포) · 상대 작업량 2/3**
원 연결: FN-33-01, FN-33-02, FN-34-01; SPEC-DESKTOP-001/002, NUMERICAL-002(외부교환).

**현재 구현 / 실제 잔여:** 공통 Core/bridge 와각진입점이있다. 별도 MCP 편집엔진이나 LLM 필수서비스를추가하지않는다.

**고정 지원 profile:** W, COMMANDS

**사용자 입력 → 조작 → 출력·저장재개:** 선언된명령목록을 registry 에서열거 → 각진입점에서같은명시 store/doc/session·입력으로 inspect/edit/run/save/read → response/evidence/오류상태비교 → late/retry/cancel·coldread.

**수정 파일·서비스 / 재사용 경로:** caelab/workbench.py; caelab/workbench_client.py; 기존 cli/public Python API; openscience/workbench_mcp.py; root 단독소유

**의존:** 각도구의기존명령; 새 leaf 는인도때자기 operation 만추가

**최소 확인 / 실패·취소 반례:** 조회전수 registry 대조는실행 0; 변경한쓰기는대표한개씩동일 owner 에서확인. unknowncommand·stale/duplicateID·타 store·권한오류. GUIonly 동작을 API 지원으로발명금지.

**종료조건:** 표 COMMANDS 의지원목록과실제 operation dispatch/대상/실패동등성이일치하면종료. native 내부모든임의메뉴의 MCP 복제는범위밖.


### B8.6.L03 — 전체 앱의 종료 가능한 실제 사용 동선

**분류 A · 단독 책임 T7(독립 실행·연결·이동사본·Windows 배포) · 상대 작업량 3/3**
원 연결: FN-33-01, FN-33-02, FN-34-01; SPEC-DESKTOP-001/002, NUMERICAL-002(외부교환).

**현재 구현 / 실제 잔여:** 기능별 GUI 코드는각팀이계속작성중이다. 이행은새디자인회차가아니라 PRODUCT_PLAN 의원형화면·§13.2 사용성인수의공통끝점이다.

**고정 지원 profile:** W, DOCS

**사용자 입력 → 조작 → 출력·저장재개:** 각독립앱에서파일/새문서 → 선택항목편집 → Check/preview/Apply·실제표/곡선/native3D → 실패위치복귀·취소 → 저장·재개 → 필요한정확 owner 전달. 전체폼/내부 JSON 을주작업면으로쓰지않음.

**수정 파일·서비스 / 재사용 경로:** 각팀의기존 apps/research 또는 desktop_pre/post 창; 공통 menu/action·status 는 root 소유. 기능본코드는해당팀단독

**의존:** 모든비외부 leaf 의기능인도; 각창인수는완성즉시병렬로축적

**최소 확인 / 실패·취소 반례:** 1440×900/1920×1080 및좁은창, 기존지정 DPI 와확대 1회. 키보드/포커스·단위·선택·미적용·미결정·요청미확인·부분저장·종료실패. 실제 OS 입력과 offscreen 검사분리.

**종료조건:** 지원목록의필수업무에사용을막는 GUI 결함 0, 다섯통합장면/17UC 누락 0, 짧은한국어시작예제와게시기능동등. 꾸밈개선취향은후속확장으로분리.



## 6. 일곱 팀의 병렬 배정과 단독 파일 소유

Pro 는 이 종료 명세와 중요한 물리/계약 판단을 맡는다. **일반 본코드·GUI·관련 검사·사용법은 기존 Sol 담당이 병렬 작성**한다. Codex 는 공통 경계·배정·통합·게시, Astra 는 핵심 의미·반례의 독립 검토다. 옛 §11 의 “모든 핵심 코드를 Pro 에 직렬 위임”은 최신 역할 지시로 대체한다. 이미 Pro 가 작성·인도한 코드는 저작과 실제 검증 기록을 유지한다.

팀은 소유영역이지 동시에 일곱 명 또는 특정 provider 호출을 강제하는 숫자가 아니다. 실제 슬롯·기존 담당은 Codex 현재 환경에서 배정한다. 아래의 전용 쓰기 소유와 실제 활성 담당을 매핑하고 기존 WIP 파일을 옛 main 으로 덮지 않는다.

| 팀 | 고정 책임 | D | A | E | 상대량 합계 | 병렬/소유 경계 |
|---|---|---:|---:|---:|---:|---|
| T1 CAD·조립·구조요소 | 해당 leaf 의 전용 코드·창·검사 | 5 | 2 | 0 | 19 | 기존 native Pre/Sol 소유 유지. M/E 전용 helper·panel 과 B32R 관측 계약을 담당한다. |
| T2 접촉·비선형·동해석·충격·Runner | 해당 leaf 의 전용 코드·창·검사 | 11 | 10 | 3 | 60 | 기존 solver/impact 담당의 파일소유를 보존. 접촉/S2 와 Impact A/B/C 는 같은 팀 안에서도 전용 파일로 병렬, 공유 adapter 는 root 만 병합한다. |
| T3 Post·비교·측정 | 해당 leaf 의 전용 코드·창·검사 | 6 | 2 | 0 | 18 | 기존 native_post_delivery 의 응력 변환 소유 유지. 비교·고차 측정·원자료 복귀 전용 모듈을 담당한다. |
| T4 Data·Material·구성식 FE | 해당 leaf 의 전용 코드·창·검사 | 2 | 6 | 0 | 19 | 기존 processing/fit/finite/LAW FE 를 재사용. MFront FE interface 와 Case C thermal-region 전용 파일을 담당한다. |
| T5 Numerical·PDE·field 전달 | 해당 leaf 의 전용 코드·창·검사 | 4 | 5 | 0 | 24 | 기존 Numerical/Picard/adjoint 를 재사용하고 유한한 네 field port 를 작성한다. B5.6/B6.4 는 한 소유자. |
| T6 Study·Expert·실험·Report | 해당 leaf 의 전용 코드·창·검사 | 2 | 4 | 1 | 16 | 기존 dynamic_reprocess_gui 의 B−A 불확실성 작업 소유 유지. 공통 취득 계약·Study/Report 소비를 담당한다. |
| T7 독립 실행·연결·이동사본·Windows 배포 | 해당 leaf 의 전용 코드·창·검사 | 0 | 8 | 0 | 21 | 기존 설치/SDK Sol 을 유지. 공통 Core/owner/registry/transport 와 root scripts 의 실제 병합 책임은 Codex 다. |

상대량 1/2/3 은 연결/기존 경로 수용, 여러 파일의 의미 있는 연결, native 또는 상태/물리 계약 변경을 구분한 **복잡도 표시**다. 일수·시간·인원 예측이 아니며 71 개를 같은 크기로 보지 않는다. T2 는 leaf 수와 native 상태 변경이 가장 많다. 같은 T2 안에서도 아래 전용 소유자를 분리해 접촉 전체가 끝날 때까지 Impact/동해석을 기다리게 하지 않는다.

### 6.1 전용 쓰기 소유자

| 논리 소유자 | 배정 범위 | 파일 단독 규칙 |
|---|---|---|
| T1-Motion | B1.2 | motion_*만. M4 원 geometry/owner 는 유지 |
| T1-Elements | B1.3–4 | shell/beam/laminate/초기장/connector/pretension 전용 파일. shell_results/기존 freeze 공통 hunk 는 root |
| T2-Contact | B1.5, B1.6.L01/L03 | 새 Aster contact/cohesive/user-model helper 의 단독 작성. contact_aster_results 는 이 소유자 하나가 모든 소비자 요구를 반영 |
| T2-Dynamic | B1.6.L02, B2.1–4 | 기존 dynamic/restart/reader 의미. Runner 공통은 root |
| T2-Impact-A | B2.5 | INP/native RAD 입력 전용 helper. B 의 material/deck 계약을 소비 |
| T2-Impact-B | B2.6.L01–04 | bulk/interface/history/reclosure/TH 전용 helper. 기존 A admission/model/adapter 는 root 최소 hunk |
| T2-Fatigue | B2.6.L05 | 기존 fatigue core/dialog 의 인수·발견 결함. 손상법칙 파일에 fatigue 재명명 금지 |
| T2-Remote | B8.4 | 기존 remote/external scheduler 포트. JobManager 생명주기는 root |
| T3-Comparison | B3.2 | `native_post_delivery`의 응력 4 변환 작업 소유를 먼저 유지. 나머지 strain/spatial helper 는 그 공유 계약을 사용 |
| T3-Measurement | B3.1.L01/B3.3/B3.4 | 고차 surface/block/current geometry 와 원행 선택. Workspace/bridge/shared chart 는 root hunk |
| T4-DataMaterial | B4.1–4 | 기존 Data/Plan 소비와 후보 보존. numerical.py·MaterialDocuments 공통은 root |
| T4-LawFE | B4.5/B6.1 | 기존 LAW FE·새 thermal-regions·MFront FE integration. 한 파일은 이 소유자만 수정 |
| T5-Numerical | B5, B6.4 | 기존 Numerical/adjoint/Picard 의 인수·교정. engine 공통 변경은 root 에 제출 |
| T5-PDEPorts | B6.2–3 | 모든 새 structural_field_ports/transfer 의 단독 작성. B1 initial field 와 계약만 공동 합의 |
| T6-Uncertainty | B7.3 | `dynamic_reprocess_gui`의 실제 B−A 연결 작업을 보존. 전파 엔진 재작성 금지 |
| T6-Research | B7.1/2/4/5 | exact Study/Expert/진단/Report 소비; B3 origin handler 는 상대 소유자에 요청 |
| T6-Acquisition | B7.6 | 공통 sample/session/replay 및 나중 실제 device binding |
| T7-Desktop | B8.1–3/5/6 | owner/copy/link/배포 인수. 실제 공통 Core 는 Codex |
| T7-NativeClose | B3.1.L02 | 기존 SDK/managed-close 소유 유지. stock PV 기능은 기다리지 않음 |

“논리 소유자”는 새로운 팀/도구/프레임워크가 아니다. 현재 Sol 이 한 소유자를 맡거나 여러 소유자의 순차 작업을 맡을 수 있다. 같은 파일의 활성 쓰기 담당은 반드시 한 명이다. 담당 실명이 이 패킷에 없는 경우 가짜 활동 기록을 만들지 않는다.

### 6.2 Codex 만 병합하는 공통 파일

`caelab/workbench.py`, `workbench_client.py`, `material_document.py`와 공통 owner 상속 기반, storage/registry/registration/native_commands/transport, 공통 JobManager/실행 제어, GUI desktop dispatch/CLI/MCP/routes 는 Codex 단독 통합이다. `numerical.py`/Plan compiler, `evaluation_definition.py`, `contact_steps.py`/contact deck/freeze, 공통 FRD/VTK reader, `impact_model.py`/admission/adapter, Post `workspace.py`와 공통 native bridge 는 도메인 작성자가 기능 hunk 를 제출하되 최신 main 에 대한 적용/병합은 root 가 순차 수행한다.

한 전용 파일을 여러 leaf 가 소비하면 최초 지정 소유자가 유지한다. 소비자는 함수를 별도 복제하거나 전체 파일을 덮지 않고 입력/출력·실패 반례와 최소 hunk 를 요청한다. `product.patch`와 공통 `integration.patch` 또는 동등한 작은 commit 을 분리하며, 보호된 Sol WIP/원 실패/원 benchmark threshold 를 보존한다.

### 6.3 실제 실행 순서

| 파동 | 동시에 할 일 | 통합 조건·즉시 인도 |
|---|---|---|
| P0 현재 상태 보존 | Codex 가 71ID↔현 active 담당/파일을 붙이고 현재 두 Sol WIP 를 계속 진행. 읽기용 작은 port sample 과 owner/source/state 계약만 맞춤 | 기존 전체 suite/Pro 추가 승인/SDK 를 대기하지 않는다. 이 문서는 바로 작업카드가 된다 |
| P1 기존 사용 닫기 + 독립 core | 각 팀 A 증거 대조·누락 실제 인수 병렬. T1 E3–6, T2 contact·A 입력·B 이력·동해석, T3 두 변환/측정, T4 MFront/thermal, T5 네 port, T6 uncertainty/acquisition 병렬 | leaf 가 같은 입력→결과→저장/오류를 닫으면 독립 인도. A 의 이미 유효한 증거가 있으면 재실행 없이 연결하고 종료 |
| P2 공급/소비 접점 | T2 새 law/contact 결과→T3 소비, T4 LAW thermal↔T5 T port, T3 측정/변환↔T6 B−A, T1 conditions↔T2 runner, 각 도구↔T7 save/portable | 공통 파일 hunk 만 Codex 순차. 공급자 함수 전체 완성까지 기다리지 않고 고정된 record 로 consumer 개발 |
| P3 통합장면 | 아래 S1–S5 를 관련 기능이 닫히는 순서에 한 번씩 실행. 이미 완료한 장면의 무관한 solver 는 재실행하지 않음 | 변경 영향이 없는 장면은 마지막 입력/결과를 재사용. 모든 비외부 67·필수결함 0·traceability 충족 시 SOFTWARE_CLOSED |
| P4외부 연결 | 실제 허가 장비/SSH/Slurm/OpenPBS 가 제공된 해당 E 만 수행 | 외부 host/device 마다 고유 종료 증거. 그 전에는 소프트웨어 범위 완료와 외부 인수 미완료를 분리 |

**Critical path 1:** T2 user Aster/state→hard/cohesive/해제·결과 + T4 thermal-regions + T5 T3D→Case C/S3. 세 갈래는 독립 작성 후 계약에서 합류한다.
**Critical path 2:** T2 부분 손상 loop→native deletion/contact 활성 정책→TH/원 상태·피로 소비→S4. 삭제표본 후 지연 TYPE24 만으로 넘어가지 않는다.
**Critical path 3:** T1 B32R native 관측 원문·정체성→reader→해당 출력 build 배포. 기본 shell/beam/지그 사용을 막지 않는 별도 capability 다.
**공통 마지막 관문:** T7 exact source/runtime closure·새 PC·managed-close/저장·전체 실사용. SDK 는 자기 close 기능 및 해당 배포 인수의 선행일 뿐 다른 66 기능의 선행이 아니다.

### 6.4 중간 인도의 끝

완성한 leaf 마다 실제 source/최소 공통 hunk, 변경 baseline·파일 manifest, 정상/대표 실패·취소·cold 결과, 공개 작은 입력, 한국어 5–10 단계 사용법을 함께 게시한다. 코드 작성/정적 검사/controlled fixture/native 계산/실제 OS 조작을 구별한다. 전용 helper 존재나 다운로드 ZIP 생성 자체는 CLOSED 가 아니다. 미완성 다른 부모를 이유로 완료 leaf 의 인도를 묶어 두지 않는다.


## 7. 마지막 다섯 통합장면 — 추가 작업 개수로 세지 않음

아래 S1–S5 는 §11 의 I0–I4 병합 지점과 혼동하지 않도록 다른 이름을 쓴다. 새 여섯 번째 장면을 계속 추가하지 않는다. 각 장면에 준비된 원 입력·관측 위치·지원 profile·수치 기준과 책임 owner 를 연결한다. 기본 양성 사례와 해당 장면의 치명적 실패 한 개를 같은 작은 자료에서 수행하고 마지막에 source store 없는 읽기 또는 정확 owner cold read 를 확인한다.

| 장면 | 실제로 수행할 끝-to-끝 | 선행 leaf / 책임 | 그 장면이 닫히는 증거 |
|---|---|---|---|
| S1 구조·설계/Case B | FreeCAD 자기 CAD·반복 occurrence→M4 독립 FE→표현/재료·힘/편심·체결·필요 접촉→실제 solver→Post 동일 gauge→typed DOE/후보→명시 설계 반영→저장·새 owner | 기존 B1.1 + B1.2/1.3/1.4/1.5/1.6 중 선언 profile, B3, B5.1/.3, B8.1/.2; T1/T2 공급·T3/T5 소비 | 실제 모델/선택/원값·후보 계보, 원 CAD 불변, stale mesh/잘못된 occurrence 거절, 후보 채택 취소·저장 재개. 이 장면 하나로 모든 connector 조합을 수용하지는 않음 |
| S2 자료·재료·시험/Case A | raw Data→교정/처리→같은 관측량→Material protocol→다시험 fit/독립 holdout→J2·명시 DP FE→동일 gauge/측도 비교·B−A 불확실성→국소 식별 진단/다음시험→Study·Report→cold | B4.1–5, B6.1 의 기존 law 의미, B3.2/.3/.4, B7.3/.4/.5, B8.2; T4/T6 | 원행/시간/단위·fit/holdout 분리, 실제 FE 와 추정 구별, 공분산 미제공 UNKNOWN, 마지막 계획/본문/원결과 일치. 원 후보를 숨은 재평가로 바꾸지 않음 |
| S3 PDE·다분야/Case C | 사용자 P1 열식/IC·BC→실제 수렴 T→다른 mesh/시각의 3D receiver→열 곡률/Maxwell hold·회복 및 Aster HEXA8/CZM_LIN_REG 계면 손상·재닫힘→Evaluation/Picard→MDO→Post/Study/저장 | B4.5.L02, B6.2/.3, B1.5.L02, B5.6.L01; T5 계약·T4/T2 공급 | Tref 한 번, 실제 time·배향·coverage, 상이 solver 상태 명시 전달, 후보/반복 초기화, unconverged field 거절. FELUPE bonded thermal/Maxwell 은 비교 variant 로 남고 Aster 계면과 상태 연속을 공유하지 않는다. LAW117 과 완전삭제 후 재접촉은 S4 에서 유지한다. |
| S4 동역학·손상 | 정적 accepted state→CCX dynamic→같은 native checkpoint continuation 또는 명시 다른 새 Impact 실행→bulk/cohesive/active/contact/TH force·sample impulse/energy→εN/CP fatigue→Post/Study→실패자료 재후처리·cold | B2.1–6, B1.6, B3, B7.5; T2 공급 | restart/rerun 구분, 실제 partial loop·완전삭제 재접촉, 실패 raw/prefix·gap·terminal 불변, 없는 native 채널 합성 0, cold solver/provider0. CCX checkpoint 를 OpenCourant continuation 으로 표시하지 않음 |
| S5 독립·자동화·배포 | 9 Research owner+Pre/Post 독립 진입·외부결과·Study 단독→GUI/CLI/Python/MCP exact owner→관련저장 실패/복구→portable→원 store 제거 후 새 Windows 읽기·편집/재저장 | B8 전 A, B3.1 close 의 별도 profile, 각 tool 의 완료 leaf; T7/Codex | WSL/CAD/AI 없는 연구 업무, stock native 기본 사용, wrong store/late ack/partial save 보존, 실제 파일연결·한글경로·OS 입력, runtime/라이선스 일치. 네 E 가 미제공이면 live 장비/host 성공은 별도로 미완료 |

새 solver campaign 은 S1–S5 전체를 반복하는 방식이 아니다. 새 law/출력/mapping 만 사전에 정한 작은 native 수용을 하고, 마지막 통합에서는 그 보존 결과로 대체 가능한 계산을 반복하지 않는다. 실제 native 연속 상태가 요구되는 S3/S4 의 연결은 보존 결과만 붙여 수용한 척하지 않는다.


## 8. 변경·결함·외부조건으로 종료점이 이동하지 않게 하는 규칙

**기존 요구의 누락**은 연결된 현재 leaf 의 acceptance 누락으로 등록한다. 같은 사용자 결과를 완성하기 위한 추가 함수·채널·반례는 새 기능 수로 계산하지 않는다. A 에서 필수 코드가 발견되면 같은 ID 가 D 가 되며 71 합계는 유지된다.

**구현 결함**은 정확 baseline/파일/입력/원 결과/기대값/실패 반례를 붙인다. 데이터 소실, 잘못된 물리량·단위, 자동 재실행/잘못된 owner, mandatory 사용 차단은 해당 leaf 의 종료를 막는다. 무관한 팀/기존 완료 기능은 계속한다. 원 실패 값·기준을 낮추거나 test 를 삭제해 닫지 않는다.

**후속 확장**은 이 문서의 profile 밖인 solver/요소/법칙, 새로운 통신 장비군·임의 포맷, 모든 조합의 곱집합, 새 GUI 취향·성능 목표다. 기존 원 FN/AC 에 필수로 명시되어 있지 않으면 후속 version 으로 분리하고 71 의 종료점을 바꾸지 않는다. 반대로 원 FN/AC 의 필수 결과가 빠졌다는 근거가 있으면 후속 확장이라고 밀어낼 수 없다.

기존 어떤 leaf 에도 귀속되지 않는 필수 사용자 결과를 실제 원문에서 발견한 경우만 독립 finding→Pro 설계 교정→Astra 검토→Codex 가 범위 차이/이유/계수 변경을 한 번 기록한다. 이를 매 함수·버튼 수정의 승인 절차로 쓰지 않는다. 범위 변경이 필요하다는 가능성이 현재 71 개를 무기한 미정으로 만든다는 뜻도 아니다.

**물리/환경 한계:** 수치 channel 미출력, 임의 재료 교정 없음, solver/plugin 미설치, 권한 미제공은 구별한다. 목표 profile 에 필수로 정한 채널이 없으면 D 미완료다. 공학 판단의 원 관측·교정이 없는 경우에는 실행한 software 가 닫혀도 engineering UNKNOWN 은 그대로다. 새 PC/SDK/소프트웨어 packaging 은 E 로 옮길 수 없다.

**관리 문서의 단일 현재값:** 실제 진행/분류·owner/남은 defect·증거 링크는 CURRENT_STATE 의 leaf ID 기록 한 곳에 둔다. 이 파일은 scope/exit 기준이다. MoAI/SPEC/todo/README 는 그 상태에 동기화하며 task 체크 자체를 수용 증거로 쓰지 않는다. 과거 운영 문서의 슬롯/담당/계획을 현재로 자동 복원하지 않는다.

**프로세스와 재시도:** 작은 실행은 test store·자기 child PID/handle 만 소유하고 정상/실패/timeout 모두 finally 에서 정리한다. 정리 미확인은 실패다. 프로세스 이름 전체 kill, 임의 사용자 창 종료, same-command 가 미확인인 상태에서 새 solver/provider 제출은 금지한다. 제품 창 닫기·Job 취소·장비 physical stop 은 서로 다르다.


## 부록 A. 74개 FN 원행의 보존·종료 연결

원문은 `docs/IMPLEMENTATION_DELIVERIES.md` 부록 A 의 74 행이다. 아래 마지막 열은 그 원행 종료조건을 보존한다. 과거 “현재/추가개발/완료 대조” 상태는 최신 상태로 복원하지 않는다. **동일 parent 의 leaf 전부 + 원행의 실제 해당 조건**으로 닫으며, 기존 보존 범위는 관련 통합장면과 변경 영향 회귀만 확인한다. 한 FN 이 여러 parent 를 쓰더라도 leaf 개수는 중복하지 않는다.

| FN | 현재 연결 parent / leaf 집합 | 기존 SPEC/원요구·AC | 원문 종료조건 |
|---|---|---|---|
| FN-10-01 | B1.1(기존보존/공동증거) | §3 보존·I1; PREFE AC-01; R04;R06;R07;R08;R25;R26 / AC-D03;AC-D11 | constraint 재정렬 뒤 같은 semantic target 또는 명시 수리; 원 CAD 보존 |
| FN-10-02 | B1.1(기존보존/공동증거) | §3 보존·I1; PREFE AC-02; R04;R06;R07;R08;R25;R26 / AC-D03;AC-D11 | 무반응 관측이 전역 free 변수 금지로 확대되지 않음 |
| FN-11-01 | B1.1(기존보존/공동증거); B1.2: L01 | B1.1–2; PREFE AC-03; R01;R07;R11;R12;R26;U§6 / AC-D03;AC-D11 | old restore 가 새로운 P1 adoption 을 되돌리지 못함 |
| FN-11-02 | B1.2: L01 | B1.1–2 관련 회귀; PREFE AC-04; R01;R07;R11;R12;R26;U§6 / AC-D03;AC-D11 | cancel request/unsupported/terminal/restore 를 실제 native 상태로 표시 |
| FN-12-01 | B1.4: L01,L02,L03,L04 | B1.3–4 관련 회귀; PREFE AC-05; R01;R08;R19;R26;R29;R30 / AC-D03;AC-D11 | 잘못된 body/face·중복/누락을 3D 와 table 에서 함께 수정 |
| FN-12-02 | B1.3: L01,L02; B1.4: L01,L02,L03,L04; B2.1: L01 | B1.3–4·B2.1; PREFE AC-06; R01;R08;R19;R26;R29;R30 / AC-D03;AC-D11 | 지원되지 않는 card 는 draft 저장·실행 차단; raw include 보존 |
| FN-13-01 | B1.1(기존보존/공동증거) | §3 보존·I1; PREFE AC-07; R08;R09;R26;R29;R34 / AC-D03;AC-D11 | 불량 element 를 선택·격리·수정·재생성·비교 |
| FN-13-02 | B1.1(기존보존/공동증거) | §3 보존·I1; PREFE AC-08; R08;R09;R26;R29;R34 / AC-D03;AC-D11 | stale mesh 는 보존되고 적용하지 않음; 취소와 종료 구분 |
| FN-14-01 | B1.5: L01,L02,L03,L04,L05,L06 | B1.5; PREFE AC-09; R01;R08;R19;R26;R29;R30 / AC-D03;AC-D11;AC-D04 | 두 set/normal arrows/실제 gap 과 입력 policy 확인; 미지원 저장 가능·run block |
| FN-14-02 | B1.6: L01,L02,L03; B3.3: L01,L02,L03 | B1.6·B3.3; PREFE AC-10; R01;R08;R19;R26;R29;R30 / AC-D03;AC-D11;AC-D04 | 실제 pressure/force/gap/slip 의 단위·위치·부호·time 를 독립 검증 |
| FN-14-03 | B1.5: L01,L02,L03,L04,L05,L06; B3.4: L01 | B1.5 관련 회귀; PREFE AC-11; R01;R08;R19;R26;R29;R30 / AC-D03;AC-D11;AC-D04 | Cancel 은 old refs unresolved 유지; Apply 는 새 geometry/contact rev 와 재 preflight |
| FN-15-01 | B1.6: L01,L02,L03; B2.1: L01 | B1.6·B2.1–4; PREFE AC-12; R01;R14;R26;R29 / AC-D03;AC-D11;AC-D04 | 물리 time/iteration/walltime 분리; 실패 increment→원설정 수정 |
| FN-15-02 | B1.6: L01,L02,L03; B2.1: L01; B2.3: L01 | B1.6·B2.1–4; PREFE AC-13; R01;R14;R26;R29 / AC-D03;AC-D11;AC-D04 | 각 physics 기준을 충족한 조합만 run enabled; 다른 도구의 선행 gate 없음 |
| FN-25-01 | B2.3: L01; B8.4: L01,L02,L03,L04 | §3 보존·B2.3; PREFE AC-14; R08;R12;R20;R21;R34 / AC-D03;AC-D11;AC-D06 | 같은 job/result/input 을 열고 status 관측만으로 submit 없음 |
| FN-25-02 | B2.3: L01; B2.4: L01 | §3 보존·B2.4; PREFE AC-15; R08;R12;R20;R21;R34 / AC-D03;AC-D11;AC-D06 | 늦은 결과 보존; 종료 미확인 자동 retry/kill 금지 |
| FN-16-01 | B2.5: L01,L02 | B2.5; IMPACT FN-16-01; R01;R15;R30 / AC-D03;AC-D11 | 미지원 card 누락 없이 차단; 측정 v/ω와 height-derived mode 분리 |
| FN-16-02 | B2.3: L01; B2.6: L01,L02,L03,L04,L05 | B2.6·B3; IMPACT FN-16-02; R01;R15;R30 / AC-D03;AC-D11 | 정확 physical time·added mass·energy balance·failure 및 원값을 남김 |
| FN-17-01 | B2.6: L01,L02,L03,L04,L05; B1.5: L01,L02,L03,L04,L05,L06 | B2.6·B1.5; IMPACT FN-17-01; R01;R17;R29;R30;R31 / AC-D03;AC-D11 | bulk 와 interface damage·reclosure 결과를 따로 추적 |
| FN-17-02 | B2.6: L01,L02,L03,L04,L05 | B2.6; IMPACT FN-17-02; R01;R17;R29;R30;R31 / AC-D03;AC-D11 | 단일 cycle 을 수명으로 표시하지 않고 요구/미확인 보존 |
| FN-27-01 | B3.1: L01,L02; B3.3: L01,L02,L03 | B3.1·3; POST-COMPARE; §5; R10;R12;R13;R20 / AC-D03;AC-D11 | 정확 source/time/association↔3D/표/곡선 선택 일치 |
| FN-27-02 | B3.1: L01,L02 | B3.1; POST-COMPARE; §5; R10;R12;R13;R20 / AC-D03;AC-D11 | 관리 Ctrl+S/close save 가 동일 관문; native stock 설정은 별도 |
| FN-28-01 | B3.2: L01,L02,L03 | B3.2 관련 회귀; POST-COMPARE; §5; R10;R11;R19;R20;R34 / AC-D03;AC-D11 | 동일 tet 또는 B→A scalar 만 지원; percent mask 와 delta mask 구분 |
| FN-28-02 | B3.2: L01,L02,L03 | B3.2; POST-COMPARE; §5; R10;R11;R19;R20;R34 / AC-D03;AC-D11 | 필수 F/J·coordinate/time mapping 없으면 해당 field diff 차단 |
| FN-28-03 | B3.4: L01 | B3.4; POST-COMPARE; §5; R10;R11;R19;R20;R34 / AC-D03;AC-D11 | 원 A 정상 유지·새 B branch 로만 변경; retained old result 보존 |
| FN-03-01 | B4.2: L01; B4.6(기존보존/공동증거) | B4.6; §6 SPEC 연결; R10;R12;R19;R20;R32;U§5;U§6 / AC-D03;AC-D11 | B 1250 µm→1.25 mm, 0.01 kN→10 N, 1000 ms→1 s 를 원행과 대조 |
| FN-03-02 | B4.2: L01 | B4.2; §6 SPEC 연결; R10;R12;R19;R20;R32;U§5;U§6 / AC-D03;AC-D11 | 현재면적/J 없이 true stress 요청은 차단; invalid draft 저장 |
| FN-04-01 | B4.1: L01; B4.6(기존보존/공동증거) | B4.6; §6 SPEC 연결; R10;R12;R20;R32;U§6 / AC-D03;AC-D11 | hide 가 통계 제외를 바꾸지 않고 mask Undo 는 원 row 를 보존 |
| FN-04-02 | B4.1: L01 | B4.1; §6 SPEC 연결; R10;R12;R20;R32;U§6 / AC-D03;AC-D11 | 비단조·gap·NaN 원자료 보존; 허용된 연산만 실행; 큰 파일 전체 UI reload 방지 |
| FN-04-03 | B4.1: L01; B4.4: L01; B4.6(기존보존/공동증거) | B4.6; §6 SPEC 연결; R10;R12;R20;R32;U§6 / AC-D03;AC-D11 | 품질 제외 finite sample·Plan 제외 sample 은 raw/화면에 남되 objective 에 포함되지 않음; hide 와 holdout 독립 |
| FN-06-01 | B4.2: L01; B4.3: L01 | B4.2–3; §6 SPEC 연결; R01;R17;R20;R29 / AC-D03;AC-D11 | 현재 실제 F·time·stress measure 를 저장 결과에서 확인 |
| FN-06-02 | B4.3: L01 | B4.3; §6 SPEC 연결; R01;R17;R20;R29 / AC-D03;AC-D11 | 동일 axial stretch 에서 자유 횡응력≈0; 고정 F22/33 와 구별; 실패 state 보존 |
| FN-07-01 | B4.3: L01; B8.2: L01; B4.6(기존보존/공동증거) | B4.6·B8.2; §6 SPEC 연결; R01;R17;R18;R20;R27;R32 / AC-D03;AC-D11 | Material+Plan 동시 dirty·trial roles·정확 source ref 를 한 화면에서 편집 |
| FN-07-02 | B4.4: L01 | B4.4; §6 SPEC 연결; R01;R17;R18;R20;R27;R32 / AC-D03;AC-D11 | 없는 곡선/holdout 은 없음 표시; 행 선택 무계산; 명시 평가만 새 ref, source masks 실제 objective 적용 |
| FN-07-03 | B4.4: L01; B4.6(기존보존/공동증거) | B4.6; §6 SPEC 연결; R01;R17;R18;R20;R27;R32 / AC-D03;AC-D11 | r17 fit 결과를 r18 에 silent overwrite 하지 않고 새 revision 과 provenance 를 보존 |
| FN-09-01 | B4.5: L01,L02; B6.1: L01,L02 | B4.5·B6.1; §6 SPEC 연결; R17;R19;R26;R29;R30 / AC-D03;AC-D11 | 미지원 조합·누락 failure 계수를 숨기지 않고 export 차단 |
| FN-09-02 | B4.5: L01,L02; B6.1: L01,L02; B4.6(기존보존/공동증거) | B4.6; §6 SPEC 연결; R17;R19;R26;R29;R30 / AC-D03;AC-D11 | 성공 exit 와 stress/strain/energy 동등성 구분 |
| FN-20-01 | B5.1: L01 | B5.1; NUMERICAL-002; §7; R18;R27;R31;R40 / AC-D03;AC-D11;AC-D04 | 행 선택→원입력/응답, rank deficient 표시와 failed 후보 보존 |
| FN-20-02 | B5.2(기존보존/공동증거) | B5.2; NUMERICAL-002; §7; R18;R27;R31;R40 / AC-D03;AC-D11;AC-D04 | ordinary LHS/누락 결과/순서 변경은 Sobol 차단 |
| FN-20-03 | B5.1: L01 | B5.1; NUMERICAL-002; §7; R18;R27;R31;R40 / AC-D03;AC-D11;AC-D04 | 종속/비연속 변수를 continuous rounding 으로 속이지 않음 |
| FN-21-01 | B5.3: L01 | B5.3; NUMERICAL-002; §7; R18;R27;R31;R32 / AC-D03;AC-D11;AC-D04 | 가짜 응답·penalty 혼입 없이 best feasible/failed/infeasible 구분 |
| FN-21-02 | B5.4: L01 | B5.4; NUMERICAL-002; §7; R18;R27;R31;R32 / AC-D03;AC-D11;AC-D04 | gradient 지원이 없으면 해당 method 만 unavailable; 일반 search 유지 |
| FN-22-01 | B5.2(기존보존/공동증거) | B5.2; NUMERICAL-002; §7; R18;R31;R32 / AC-D03;AC-D11 | 실패 표본 포함 전체 수·조건부 통계·tail bounds 를 표시 |
| FN-22-02 | B5.2(기존보존/공동증거) | B5.2; NUMERICAL-002; §7; R18;R31;R32 / AC-D03;AC-D11 | PSD/unit/순서 검사; correlation 미지원이면 explicit block |
| FN-23-01 | B5.5(기존보존/공동증거) | B5.5; NUMERICAL-002; §7; R18;R31 / AC-D03;AC-D11 | 학습점 중복 거절·out_of_range 와 PREDICTED 명시 |
| FN-23-02 | B5.6: L01 | B5.6; NUMERICAL-002; §7; R18;R31 / AC-D03;AC-D11 | 재열기 숨은 학습/solve 없음; 확인 결과는 새 evaluation |
| FN-24-01 | B5.6: L01 | B5.6; NUMERICAL-002; §7; R18;R31;R40 / AC-D03;AC-D11;AC-D05;AC-D07 | total budget·directions·infeasible 보존과 정확한 점/결과 |
| FN-24-02 | B5.6: L01; B6.4(기존보존/공동증거) | B5.6·B6.4; NUMERICAL-002; §7; R18;R31;R40 / AC-D03;AC-D11;AC-D05;AC-D07 | 새 scheduler 없이 domain/Plan 경계 유지·설계 동기화 검증 |
| FN-08-01 | B6.1: L01,L02 | B6.1; RESEARCH FN-08-01; R01;R17;R29;R31;R39 / AC-D03;AC-D11;AC-D05;AC-D07 | 선택 증분→state/residual/tangent 원값·입력 ref 를 조회 |
| FN-08-02 | B6.1: L01,L02; B4.5: L01,L02 | B6.1·B4.5; RESEARCH FN-08-02; R01;R17;R29;R31;R39 / AC-D03;AC-D11;AC-D05;AC-D07 | 지원 pair/finite strain/interface 별 증거가 없으면 해당 실행·export 차단 |
| FN-18-01 | B6.2: L01 | B6.2; RESEARCH FN-18-01; R01;R16;R28;R31 / AC-D03;AC-D11;AC-D04 | 현재 bounded AST/unit1 를 정확히 보여주고 declared input 을 바꿈 |
| FN-18-02 | B6.2: L01 | B6.2; RESEARCH FN-18-02; R01;R16;R28;R31 / AC-D03;AC-D11;AC-D04 | 미지원 방정식 draft 저장·실행 차단; 지원 equation 독립 기준 충족 |
| FN-19-01 | B6.4(기존보존/공동증거) | B6.4; RESEARCH FN-19-01; R01;R16;R19;R20;R31 / AC-D03;AC-D11 | Plan 없이 같은 kind=evaluation 문서를 저장/평가·Plan 은 exact ref |
| FN-19-02 | B6.3: L01,L02,L03,L04 | B6.3; RESEARCH FN-19-02; R01;R16;R19;R20;R31 / AC-D03;AC-D11 | 스칼라 P1 온도의 mesh·시각·단위 대응은 기존 구현 재사용. 실제 공급/수신 field 와 ΔL=α(T−Tref)L 기준; ΔT offset 중복 금지. 벡터/텐서·보존 전달 잔여 |
| FN-19-03 | B6.4(기존보존/공동증거) | B6.4; RESEARCH FN-19-03; R01;R16;R19;R20;R31 / AC-D03;AC-D11 | NOT_CONVERGED 는 유효 목적값 아님; 반복 partial checkpoint 미지원 유지 |
| FN-05-01 | B7.3: L01 | B7.3; EXPERIMENT; §9; R10;R11;R20;R32 / AC-D03;AC-D11 | raw→보정값→동일 관측량→판단의 정확 refs 를 재열기 |
| FN-05-02 | B7.4: L01; B5.3: L01 | B7.4·B5.3; EXPERIMENT; §9; R10;R11;R20;R32 / AC-D03;AC-D11 | 미식별 계수는 fixed/unidentified 로 보이고 다른 시험을 기록 |
| FN-29-01 | B7.1: L01 | B7.1; EXPERT; §9; R02;R03;R10;R11;R13;R32 / AC-D03;AC-D11 | Study 단독 생성/저장; Expert 없이 판단·후속 문서 열기 |
| FN-29-02 | B7.1: L01 | B7.1; EXPERT; §9; R02;R03;R10;R11;R13;R32 / AC-D03;AC-D11 | 새 evidence 자동 decision 변경 금지; invalid ref 는 repair 가능 |
| FN-29-03 | B7.1: L01 | B7.1; EXPERT; §9; R02;R03;R10;R11;R13;R32 / AC-D03;AC-D11 | URL 만 붙여도 근거 확인됨으로 표시하지 않고 원문 위치가 열리며 누락/변경 branch 를 식별 |
| FN-30-01 | B7.2: L01 | B7.2; EXPERT; §9; R02;R03;R13;R20;R32 / AC-D03;AC-D11 | reply 대상/실제 source·provider author·Plan draft 가 보존 |
| FN-30-02 | B7.2: L01 | B7.2; EXPERT; §9; R02;R03;R13;R20;R32 / AC-D03;AC-D11 | no-provider/limit 은 drafts 유지; 유료 fallback·자동 provider 전환 금지 |
| FN-32-01 | B7.5: L01 | B7.5; EXPERIMENT; §9; R09;R10;R11;R12;R20;R32;R34;R52 / AC-D03;AC-D11 | 수치/plot/판단 source 를 재열고 실패/UNKNOWN/NOT_RELEASED 유지 |
| FN-35-01 | B7.6: L01,L02 | B7.6; EXPERIMENT; §9; R01;R31;R32;R35 / AC-D03;AC-D11 | 실측 data/장비 종료 acknowledgment·실험 input 과 보정 lineage 확인 |
| FN-01-01 | B8.1: L01 | B8.1; DESKTOP; §10; R12;R13;R21;R33;U§1;U§5 / AC-D03;AC-D11 | 동일 store/doc 는 기존 owner 활성화; 다른 store 는 구별; 결과 열기 무실행 |
| FN-01-02 | B8.3: L01 | B8.3; DESKTOP; §10; R12;R13;R21;R33;U§1;U§5 / AC-D03;AC-D11 | 이동용 사본이 원 store 없이 열리고 원본·이전 결과가 불변 |
| FN-02-01 | B8.2: L01 | B8.2; DESKTOP; §10; R08;R11;R12;R13;R19;R20;U§6 / AC-D03;AC-D11;AC-D05;AC-D07 | Enter/Esc/Undo/멀티 owner paste 가 대상 owner 만 변경 |
| FN-02-02 | B8.2: L01 | B8.2; DESKTOP; §10; R08;R11;R12;R13;R19;R20;U§6 / AC-D03;AC-D11;AC-D05;AC-D07 | Material 만 성공해도 Plan 실패와 old reference 보존; 재열기 무계산 |
| FN-02-03 | B8.2: L01 | B8.2·I0; DESKTOP; §10; R08;R11;R12;R13;R19;R20;U§6 / AC-D03;AC-D11;AC-D05;AC-D07 | 동일 필드 stale 덮어쓰기 금지; 재승인 없는 새 ID 자동 재시도 금지 |
| FN-26-01 | B8.4: L01,L02,L03,L04 | B8.4; DESKTOP; §10; R18;R31;R35 / AC-D03;AC-D11;AC-D06 | stale exchange/duplicate/값변경 거절; missing 은 NOT_EVALUATED |
| FN-26-02 | B8.4: L01,L02,L03,L04 | B8.4; DESKTOP; §10; R18;R31;R35 / AC-D03;AC-D11;AC-D06 | reconnect 에 중복 submit 없음; 실제 job termination 과 file checksum 확인 |
| FN-31-01 | B8.5: L01 | B8.5; DESKTOP; §10; R11;R13;R19;R33 / AC-D03;AC-D11 | drag/menu 동등; broken 과 new revision 별도; 원본 편집 없음 |
| FN-33-01 | B8.1: L01; B8.6: L01,L02,L03 | B8.6; DESKTOP; §10; R13;R14;R15;R16;R35;R39;U§1;U§2 / AC-D03;AC-D11 | 도구 선택 없이 파일로 바로 맞는 owner; browser 주화면 없음 |
| FN-33-02 | B8.6: L01,L02,L03 | B8.6; DESKTOP; §10; R13;R14;R15;R16;R35;R39;U§1;U§2 / AC-D03;AC-D11 | version probe 만으로 solver benchmark/GUI 수용 PASS 표시 금지 |
| FN-34-01 | B8.6: L01,L02,L03 | B8.6·I1–4; DESKTOP; §10; R02;R13;R19;R20;R21;R43 / AC-D03;AC-D11 | 같은 결과 refs·actual values/selection; fake success 나 active doc 추정 없음 |

## 부록 B. Pre22 와 실제 plan 별칭의 대응

사용자 표기의 M1–4/E1–6/C1–6/N1–3/S1–3 은 총 22 다. 현재 PREFE plan/acceptance 의 “22개 개발 묶음” 표는 M/E/C 와 R1/R2, NS1/NS2/N3/S2 를 사용한다. **이 표기 차이 때문에 R1/R2 나 NS1/NS2 를 추가 기능으로 더하지 않는다.** 원 AC-01–15 와 관련 direct acceptance 를 아래 leaf 에 연결한다.

| 원 항목 | 이번 연결 | 닫을 최소 의미 |
|---|---|---|
| M1 종속 구동 | B1.2.L01 | 실제 frame 시각의 다변수/차원/DAG·경로; 끝 자세만 맞는 것으로 경로를 닫지 않음 |
| M2 중첩 조립 | B1.2.L01 | 두 깊이·반복 occurrence 한 개 선택과 강체/가동 의미 |
| M3 닫힌 기구 | B1.2.L01 | 기존 native 4절·도달 불가/중복구동·정지복원 |
| M4 해석 후보 | B1.1 보존 / S1 | 선택 자세의 독립 편집 모델, 원 조립 불변 |
| E1 셸 | B1.3.L01 | 기존 curved/region S8 와 상하면·저장 |
| E2 빔 | B1.3.L01/L02 | RECT B32R 기존 결과 및 아직 없는 native 일반화 관측 |
| E3 적층 | B1.4.L01 | 층/각도/두께/순서·native 층 출력 |
| E4 장·초기조건 | B1.4.L02 | 힘/압력 보존·T/Tref·초기 stress/compatible strain 상태 |
| E5 연결요소 | B1.4.L03 | 병진/회전 spring-damper 의 축·단위·native DOF |
| E6 체결 | B1.4.L04 | 조임→길이 유지→외력 상태 연속 |
| C1 hard | B1.5.L01 | 진짜 비관입/상보성·원 접촉값 |
| C2 cohesive | B1.5.L02 | implicit 계면 법칙·부분손상/압축/재접촉 |
| C3 tie | B1.5.L03 | 곡면/모서리/모호성·A→B→C effective 초기좌표 |
| C4 sliding/normal | B1.5.L05 | native formulation·법선/쌍/부호 |
| C5 stage/release | B1.5.L04 | 실제 활성/해제·상태 이어짐, 치유 없음 |
| C6 periodic | B1.5.L06 | 기존 proper transform·DOF 식·누락 대응 |
| N1 재료 비선형 | B1.6.L02/L03 | 기존 J2 및 선택 Aster 비선형; NS1 에 대응 |
| N2 기하 비선형 | B1.6.L02/L03, B2.1.L01 | NLGEOM 의 실제 input/result. dynamic 와 자동 등치 아님 |
| N3 단계 전달 | B2.2.L01 | 정적 accepted state→dynamic 유지/해제 |
| S1 CalculiX 정적 | B1.6.L02 | NS1 과 같은 구현 증거를 재사용 |
| S2 Code_Aster | B1.6.L03 | 실제 사용자 model/sets/law·실패/재개 |
| S3 시간 해석 | B2.1–4 | 기존 NS2 의 dynamic/stream/실제 restart 인수 |
| R1/R2 — plan 의 결과 별칭 | B1.6.L01, B2.6.L04, B3.3/3.4 | 접촉장·정확 pair 합력/모멘트·전달. 위 22 에 더하지 않음 |

## 부록 C. 17개 UC 와 필수 A/B/C 의 누락 대조

출처는 `docs/PRODUCT_UI_MCP_PLAN.md`의 기존 UC 목록이다. UC 는 행 개수만으로 완료하지 않는다. 연결된 기능 결과와 최종 장면의 증거를 사용하며 별도의 17개 solver campaign 을 만들지 않는다.

| UC / 기존 사용자 사례 | 이 종료판의 사용자 결과 | 필수 leaf / 장면 |
|---|---|---|
| UC01 공급사 시간의존 재료 | raw/단위/시간→Maxwell 점/FE·holdout→명시 채택 | B4.1–5, B6.1, S2/S3 |
| UC02 반복 소성 | 동일 protocol/관측량의 기존 J2/DP·상태/소성 결과 비교 | B4.2–5, B1.6, S2 |
| UC03 구성식 적분·접선 | state/residual/tangent 와 작은 독립 차분·실패·보존 선택 | B6.1.L02; MFront FE 는 L01 |
| UC04 비선형 PDE | 선언 equation 의 실제 풀이/수렴·경계·비교 | B6.2.L01, B5.4.L01, S3 |
| UC05 포장 낙하 | 사용자 계층/native 입력→실제시간 충격·손상/힘/에너지 | B2.5/2.6, S4 |
| UC06 과열 불량 | 사용자 온도장→열변형·곡률·관측 비교·판단 | B6.3.L04/B4.5.L02, S3; 원 교정 부족은 UNKNOWN |
| UC07 접착 박리 | 별도 bulk/interface 손상·부분이력·완전삭제 재접촉 | B1.5.L02/B2.6.L02/L03, S3/S4 |
| UC08 접촉 수렴 | 사용자 contact law·normal·단계와 native 실패→조건 수정 | B1.5/1.6, S1/S4 |
| UC09 지그 설계 | 강성/마찰/체결/편심·같은 gauge 후보와 명시 설계 채택 | B1.4/1.5/1.6, B5.1/.3, S1 |
| UC10 실험/기존결과 상관 | 동일 위치/측도/시간/단위의 비교·B−A 불확실성 | B3.2/.3/.4, B7.3, S2 |
| UC11 공차/물성 산포 | 기존 typed DOE·상관 UQ/Sobol·실패표본·tail 범위 | B5.1 및 B5.2 보존, S1/S2 의 관련 증거 |
| UC12 다음 시험 선택 | 기존 국소 진단의 fixed/unidentified→판별 목적·Study 저장 | B7.4.L01, S2 |
| UC13 대리/다목적 | 보존 surrogate→actual 확인·3 목적 Pareto·MDO·예산 | B5.5 보존/B5.6.L01, S3 |
| UC14 불량/VOC 자문 | 독립 Study·실제 Expert·원문/결과 근거·한계/결론 | B7.1/.2/.5, S5 |
| UC15 논문 재현 | exact 문헌원문/조건·선택한실제결과·독립보고·cold | B7.1/.5, S5 |
| UC16 미세구조/연성/원격 | 기존 material/PDE/evaluation 의 명시 stage·field 전달·외부 batch/remote | B6.1–4, B8.4; 새 미세구조 생성기/전용 solver 를 자동 추가하지 않음 |
| UC17 ASCII+LLM+실제 DOE | 파일 Data→기존 선택 Expert 또는 AI 없는 Plan→typed DOE→원행/후보→Study | B4.1/B5.1/B7.1/.2, B8.6.L02, S2/S5 |

실장비 사용은 FN-35 와 B7.6 두 leaf 로 별도 보존한다. 실제 장비가 없는 상태에서 UC17 의 ASCII 파일 처리 성공을 live 취득 성공으로 계산하지 않는다. A/B/C 와 UC 는 서로 중복하는 사용자 경로이므로 분모에 더하지 않는다.


## 9. 기준 소스의 구현과 출력 의미

이 절은 현황표가 아니다. 최신 담당과 진행상태는 [CURRENT_STATE.md](../CURRENT_STATE.md) 한 곳에서 갱신한다. 이 목록은 `bb31834` 및 이미 통합된 `e76cde6`을 반영한다.

- **B3.2.L01:** stress conversion 및 B−A connection 은 구현되어 A 다. 정확 Post 선택·저장 lineage·cold 인수가 남았다. 기능 구현을 중복 배정하지 않는다.
- **B7.3.L01:** supplied covariance/fixed-axis scalar difference slice 는 통합됐다. R4 의 유한 비선형 관측 chain 은 같은 D 에 남는다.
- **E3 / B1.4.L01:** private 작성/실행은 개발 완료가 아니다. UI 층 순서는 top-to-bottom, native 순서는 역순이며 층마다 8IP 다. GLOBAL S/E 는 지원한다. 해당 경로에 COORD 를 요구하지 않는다. 4층 이상 LOCAL/COORD 는 source buffer 위험이 있어 선택 출력경로를 실제 확인한다. 이는 16 층이 불가능하다는 뜻이 아니다. 기존 S8 27IP 와 RF reader 를 E3 에 적용하지 않는다.
- **E5 / B1.4.L03:** `_workspace/native-connector-delivery/` 작성은 candidate 다. 실제 source pin `cb760c2` TYPE13, elastic C3D4 FE patch/RBODY attachment, 6 대각 k/c·국부축·질량/관성 의미를 사용한다. 코드나 덱만으로 native/제품 인수 완료라 하지 않는다.
- **E6 / B1.4.L04:** native-03 의 원값 CLOAD 600 N, 지지 FORC ±600 N, SOF −1200.021 N 을 그대로 보존한다. 선택 cut의 절점력 합 599.9996 N은 지지력과 일치하고, SOF는 복구 응력 면적분으로 재현됐다. 이를 동일한 물리량의 불일치나 중복 하중이라고 해석하지 않는다. SOF를 대표 체결 축력으로 표시하지 않는다. 선택 side 의 실제 cut FRD FORC 합을 정확히 map 하고 반대 side 는 별도 보존한다. RP U1/reaction·SOF·cut force·복원 응력면적분은 별도 물리량으로 다룬다. pretension MPC 제약은 현재 작성자/CAE 계약을 따른다. 값이나 상태를 성공으로 바꾸지 않으며 새 native campaign 을 요구하지 않는다.

## 10. 범위 이동과 종료

후속 solver/요소/법칙, 모든 조합의 곱집합, 새 장비군이나 성능 목표를 현재 종료조건에 몰래 추가하지 않는다. 원 FN/SPEC 의 필수 사용자 결과가 빠진 경우 같은 leaf 에서 이를 고친다. 실제 모델·단위·재료·강도·durability 요건이 미제공이면 해당 engineering verdict 는 UNKNOWN 이고 적용 가능한 release 는 막는다. Solver exit·CI·전문가 합의는 공학 승인이 아니다.
