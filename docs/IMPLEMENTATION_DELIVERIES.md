# Autonomous CAE Lab 전체 제품 실행계획

> 작성: 실제 ChatGPT Pro. 아래 원문은 전달 당시 소스에 대한 실행계획이다.
> 현재 구현·배정·다음 행동은 [CURRENT_STATE](../CURRENT_STATE.md)에서 확인한다.

## 현재 팀 배정에 적용하는 기준

사용자의 최신 지시에 따라 개발팀은 일곱 개로 유지한다. Pro 원문의 B1–B8은
팀 안에서 나누어 인도하는 세부 묶음이며, Numerical와 PDE/연성은 같은 팀이 맡는다.

| 개발팀 | 원문 묶음과 공유 작업 |
|---|---|
| CAD·조립·전처리 | B1 모델·조립·메시·조건; B2의 초기조건 대상 연결 |
| 구조·동해석·충격 | B1 해석 실행과 B2; B8 원격 실행 |
| 후처리·비교 | B3; B1/B2 결과와 B7 보고서 그림 전달 |
| Data·Material | B4; B8 관련 문서 부분 저장·복구 |
| Numerical·PDE·연성 | B5/B6; B4 보존 후보 상세 계산과 결과 연결 |
| Expert·Study·보고서 | B7; 실험·식별성·장비·보고서의 각 잔여 |
| 설치·공통 연결 | B8 설치·이동용 사본·선택 연결 보기 |

각 팀은 기존 지원 기능을 재사용해 자기 인도의 남은 코드를 계속 작성한다.
실제 Pro가 핵심 기능을 작성하고 Sol은 GUI·연결을 완성한다. Codex는 공통 파일의
통합을 맡으며 전용 기능을 전부 혼자 작성하지 않는다. Astra가 원행·기존 완료 조건을
독립 대조했다. 원문의 File→Exit 작성 배정은 설치된 ParaView에 Qt Python 접점과
개발 SDK가 없는 사실을 반영해 Pro의 native 핵심 작성과 Sol의 연결 작업으로 적용한다.

다음 조건은 원문에 더해 반드시 구현·인수한다.

1. **관련 문서 복구:** owner별 미확정 셀 원문·초안·저장 응답을 복구 사본에 보존한다.
   복구 초안을 남기고 닫은 뒤 새 프로세스에서 이어갈 수 있어야 하며, 복구 기록 쓰기가
   실패하면 창을 닫지 않는다. 부분 저장 성공을 이 조건의 완료로 대신하지 않는다.
2. **재표본화와 원행:** 파생 표본 ID와 실제 기여 원행·구간·가중치·처리 정의를 보존한다.
   같은 원행을 공유하는 train/holdout, 품질 제외와 gap을 통과하는 보간 반례를 확인한다.
   기존 원행 하나 대응을 새 표본의 계보로 간주하지 않으며 각 단계의 mask 순서를 명시한다.
3. **상세 결과 채택:** 요약은 그대로 열람할 수 있다. 비교·채택·보고에 실제로 사용한
   상세 근거는 보존된 정확한 참조로 새 프로세스에서 다시 읽어야 한다. 미보존 표시와
   새 상세 계산 버튼만으로 이 조건을 완료했다고 하지 않는다.

이 보완은 새 사용자 승인 대기나 전체 구현 중단 사유가 아니다. 작성 중인 Pro 응답은
중단하지 않고 반환 소스를 해당 조건에 대조해 필요한 교정을 같은 인도에서 마친다.
원문 자체의 보존본은 현재 작업 문서가 가리키는 전달 자료에 남긴다.

## Pro 실행계획 원문

**요청 ID: PRO-SYSTEM-EXECUTION-20261015-01**
**계획 기준: 2026-10-15 첨부 상태 / 실행 대상: 계속 개발 중인 Windows 제품**

이 문서는 이미 승인된 제품 구현을 끝내기 위한 실행 인계다. 새 기획 승인, 제품 범위 축소, 구현 중단을 요구하지 않는다. 아래 B1–B8은 기존 74행을 묶는 인도 단위이며 새 요구 번호나 완료율의 분모가 아니다. 세부 작업 번호도 원행 안의 실행 항목일 뿐이다.

판정 기준은 `request.md`의 최신 지시, `current/CURRENT_STATE.md`의 최신 상단과 원행 표, 원요구의 현재 효력, 전체 기능 명세, 관련 SPEC, 실제 코드 순으로 적용한다. 기준 소스는 ZIP의 `baseline/`인 `02ffc24`, `current/`는 최신 기록과 미커밋 M4 변경이다. 아래의 ‘현재’는 이 첨부를 읽어 판단한 상태이며 이 문서 작성 중 실행한 Windows 제품 검사 결과가 아니다. 구현 위치를 새로 제안한 파일은 반드시 ‘신규 제안’으로 표시했다.

## 1. 실행 결론과 사용자 인도 순서

**현재 진행 중인 M4 표현 비교 교정과 Sol의 GUI/연결 통합은 그대로 계속한다. 동시에 새 Pro NS2/N3 작성과 Data·Material 확장을 시작한다. 독립 Post, Numerical, PDE, Study/Expert는 앞선 구조해석 묶음 전체의 완료를 기다리지 않는다.**

첫 인도는 기존 지원 구조해석의 ‘편집 → 명시 실행 → 같은 결과 Post 열기 → 원 설계로 돌아가기 → 저장·새 프로세스 재열기’와 M4의 ‘선택 프레임 → 별도 편집 가능한 해석 모델’을 닫는 것이다. M4 모델 준비에는 Numerical Plan, 해석 변수 등록, 메시 생성 또는 솔버 성공을 선행 요구하지 않는다. 준비가 끝난 모델에 사용자가 메시·재료·조건을 추가하는 후속 작업을 별도로 연결한다.

### 1.1 8개 인도 묶음

| 묶음 | 사용자가 끝내는 업무 | 원행의 주 배정 | 먼저 인도할 범위 / 후속 범위 |
|---|---|---|---|
| B1 설계·조립·구조해석 | FreeCAD에서 자기 모델을 편집하고 해석 입력·결과와 설계 변경을 이어간다 | 기존 D2의 15행 | 기존 구조 왕복·M4 먼저. 다변수 기구, 요소·체결·접촉·재료 조합은 단계별 추가 |
| B2 동역학·충격·손상 | 초기 상태에서 동해석·낙하를 실행하고 힘·에너지·손상·피로를 추적한다 | 기존 D8의 4행; FN-15-01/02와 FN-12-02에 교차 기여 | NS2/N3 새 작성, 일반 충격 입력을 병행. 진짜 restart, 벌크 손상·다축 피로까지 별도 종료점 |
| B3 독립 Post와 응답 반환 | 외부 결과도 직접 열어 측정·비교하고 설계·동정에 같은 응답을 넘긴다 | 기존 D4의 5행 | File→Exit·정확한 선택 왕복 먼저. 벡터/텐서·측도·시간/공간 변환 잔여를 닫음 |
| B4 Data·Material | 시험 원행에서 처리·재료 시험·다시험 피팅·후보 채택까지 끝낸다 | 기존 D5의 12행 | 기존 피팅을 유지하며 처리 recipe·측도·혼합 제어·임의 후보 상세 보존 추가 |
| B5 Numerical | DOE·민감도·역해석·UQ·대리모델·다목적 설계를 같은 평가기로 수행한다 | 기존 D6의 11행 | 이산 변수·결과 분석부터. gradient/adjoint·반복 MDO는 B6 계약과 연결 |
| B6 구성식·PDE·연성 | 구성 적분과 사용자 식을 독립 사용하고 실제 장을 다른 물리로 전달한다 | 기존 D7의 7행 | 기존 지원 식/법칙의 독립 사용 대조. FE interface·다른 mesh/time 전달 추가 |
| B7 연구 판단·실험·보고 | 자료·문헌·계산·다자 토론을 판단과 다음 시험, 편집 보고서로 남긴다 | 기존 D3 5행 + D9 4행 | 문헌 선택·Expert 왕복·3D 보고 먼저. 불확실성·식별성·실장비는 각각 별도 작업 |
| B8 일상 사용·배포·공통 연결 | 파일로 바로 시작하고 여러 창, 이동 사본, 원격 작업을 안전하게 이어간다 | 기존 D10의 11행 | 공통 저장·열기·명령 연결은 첫 인도부터. 이동 사본·그래프·원격 확장 병행 |

주 배정은 정확히 74행이다. B2가 FN-15를 구현하거나 B3가 FN-14 결과를 표시해도 원행을 중복 계산하지 않는다. 현재 24행은 **완료 11 / 부분 12 / 완료 확인 보류 1** 그대로 보존한다. 다른 50행의 ‘추가 개발’과 ‘완료 대조’도 부록에서 분리했다. 기존 52절은 제품 기능 외에 운영 원칙·후보 조사·역사적 순서를 포함하므로 어느 숫자와도 합산하지 않는다. CSV의 `NOT_STARTED_IN_THIS_REQUEST`와 `USER_REVIEW_THEN_EXPLICIT_DEVELOPMENT_START`는 10월 12일 기획 시점의 값이며 현재 착수 제한이 아니다.

### 1.2 인도와 개발의 순서는 다르다

**착수 묶음:** Codex/Sol은 기존 통합을 계속하고, Pro는 B2의 NS2/N3와 B4의 혼합 제어·처리/보존 핵심을 병행 작성한다. B3는 저장된 외부 결과만으로 개발·인수할 수 있다. B5의 변수·분포·결과 기능은 작은 기존 평가기를, B6는 기존 ODE/법칙과 저장 field를 사용한다. B7의 문헌·보고는 실제 새 솔버 계산 없이 진행한다. B8의 공통 연결은 모든 묶음에 붙는다.

**사용자 인도 순서:** ① B1 첫 왕복·M4와 B3 저장/선택, ② B4 실제 시험 연구 및 B5 기본 연구 확장, ③ B2 동해석/충격과 B6 실제 장 전달, ④ B5 고급 탐색·B7 판단/보고 및 남은 B1/B2 물리 범위, ⑤ B8 배포·전체 왕복의 최종 확인 순이다. 이것은 게시 우선순위이며 뒤 번호의 독립 코드 작성 금지가 아니다. 먼저 끝난 독립 기능은 이 순서 때문에 보류하지 않는다.

### 1.3 완료의 세 층

‘사용 가능 인도’는 지정한 업무가 편집·실행 또는 읽기·저장·복구까지 연결됐다는 뜻이다. ‘원행 완료’는 그 행의 기존 완료 조건과 본 계획에 연결한 잔여 구현이 모두 충족됐다는 뜻이다. ‘공학적 승인’은 실제 재료·시험·공차·안전/사용 기준에 대한 별도 판단이다. S8, B32R, M3, J2 일부 성공을 부모 행 전체나 제품 승인으로 확대하지 않는다.

완료 대조 행은 새로 구현하지 않는다. 원행 기준과 기존 코드/실행을 먼저 연결하고, 그 대조에서 실제로 빠진 조작만 수정한다. 이미 닫힌 행도 이번 변경이 직접 건드린 부분만 회귀 확인한다.

## 2. 모든 작성자가 지킬 연결 계약

새 공통 프레임워크나 범용 파일 형식을 만들지 않는다. 기존 owner, `JobManager`, `workbench_client`, `desktop_links`, native bridge와 저장 형식을 유지한다. 오래된 v2의 새 `.caelab` 형식 제안보다 현재 FUNCTION_SPEC의 기존 문서/`.caepre`/FCStd/관리 Post 저장 계약을 따른다.

| 경계 | 전달할 의미와 소유권 | 막아야 할 잘못된 연결 |
|---|---|---|
| 편집 → 저장 → 실행 | 셀 buffer, owner가 수락한 draft, 저장 revision, 실행 frozen input을 구별. 도메인은 물리·수치 설정, Runner는 실행 위치·자원·수명 소유 | invalid draft를 0으로 대체, 저장이 Run을 발생, 결과 열기가 재실행 |
| CAD/기구 → FE | 원문서·개정·dependency, 정확한 occurrence 경로, 선택 frame/time/clock, 세계 좌표 형상, 별도 편집 모델 | 반복 Link를 원부품 하나로 합침, ground를 FEM 고정으로 변환, 운동 자세를 원설계에 몰래 채택 |
| Data/Material → Plan | Data의 원행/채널/품질/처리 유효 mask, Material의 law/상태/protocol, Plan의 범위·역할·weight·holdout | 표시 숨김을 계산 제외로 간주, Material 저장만으로 Plan source 자동 변경, holdout 재사용을 숨김 |
| Run → Post/응답 | 정확한 job/attempt/result, field/association/component/measure/frame, 위치, step와 실제 시각, 단위, validity, 원자료 | 다른 frame으로 대체, 실패 구간 보간, RF/절점력/접촉력/지지 반력을 같은 양으로 명명 |
| Post → 설계/Numerical | 저장한 측정 정의와 원결과를 전달. 새 설계는 동일 물리 측정의 CAD/region 참조로 재평가 | 옛 node 번호만 새 mesh에 적용, 후보 선택 중 숨은 계산, 결과가 원설계를 자동 덮어씀 |
| 분야 → Evaluation | 공급 field·수신 port, 단위/기저/위치/시간/mesh 대응과 valid mask, Tref 소유, 단계별 상태·허용 재사용 | port 타입 일치를 실제 장 전달 성공으로 취급, 반복 trial마다 누적 상태 오염 |
| Study/Expert/Report | 논점·발언과 채택 판단 분리. 문서/결과/문헌의 정확한 저장 참조와 locator. report의 선택 frame 고정 | URL만으로 확인한 근거 처리, 새 발언/새 결과가 옛 판단·보고 그림을 자동 변경 |
| GUI/CLI/Python/MCP | 기존 동일 command, 명시 owner/host/session/generation, 동일 command ID의 동일 요청 재확인 | 임의 active document, 새 ID 자동 재시도로 stale 덮어쓰기, MCP용 별도 편집 로직 |

구조·충격의 기본 계산 단위는 해당 기존 adapter 계약인 mm–N–s–Mg를 유지한다. 밀도는 Mg/mm³, 응력 MPa, 에너지 N·mm, 속도 mm/s, 가속도 mm/s², 충격량 N·s이다. 회전·각도 입력은 rad/deg 변환을 명시하고 모멘트는 N·mm로 보존한다. PDE/장 전달은 기존 SI 계약을 유지하며 길이 m, 절대온도 K와 온도차를 구별한다. 모든 도구에 단위 하나를 억지 적용하지 않고 adapter 경계에서 차원과 수치 변환을 검사한다.

## 3. B1 — 설계·조립·구조해석 인도

**사용 순서:** FreeCAD에서 부품/조립 열기 → native 스케치·피처·관절 편집 → 운동 결과 또는 설계 형상 선택 → 해석 모델·메시·조건 편집 → 입력 확인 → 명시 Run → ParaView에서 같은 결과 확인 → 설계/조건 수정 또는 후보 채택 → 저장 후 새 FreeCAD/ParaView에서 재개.

**현재 재사용:** M1/M2 저장 자세, M3 닫힌 기구, Q1 치수 참조 수리, Q2 C3D10 품질 선택/비교, native FEM 할당, S8 셸, B32R 빔, J2와 수렴 이력, 기존 contact/Runner/Post. 이 경로를 새 CAD·메시·솔버 코드로 교체하지 않는다.

### 구현 작업

| 작업 | 실제 남은 코드와 수정 지점 | 끝낼 조건 |
|---|---|---|
| B1.1 M4 편집 모델 | `current/apps/desktop_pre/assembly_pose_geometry.py::assert_same_shape`, `assembly_pose_candidate.py::validate_model/PoseCandidates._prepare`의 실제 해당 준비 경로를 교정. `Part.getShape(..., transform=True)`의 세계 형상, 단일 solid wrapper 정규화와 native 형상/요소 이력 대응을 사용. source/pose/dependency 검사는 별도로 유지 | 두 깊이 가동 하위 조립·반복 Link의 각 occurrence가 별도 편집 모델에서 선택 자세와 일치. 원 조립 불변. mesh/material/조건 추가와 저장·새 프로세스 재열기 가능 |
| B1.2 기구의 남은 일반 관계 | `motion.py`, `motion_formula.py`, `motion_history.py`, `motion_occurrence.py`의 기존 관절/시간식 확장. 여러 구동 변수의 단위·종속 순서·순환·한계 검사, 중첩 경로와 native 구동의 대응, 누락된 과거 transform은 명시 새 계산으로 생성 | 단순 비율식 밖의 종속 관계와 중첩 반복 배치에서 같은 frame/path 보존. 불능 frame·종속 순환은 실패 위치를 표시하고 이전 성공 결과/새 사용자 편집을 보존 |
| B1.3 셸·빔 잔여 | 셸 `apps/desktop_pre/shell_edit.py`, `shell_freeze.py`, `caelab/adapters/shell_deck.py`, `shell_results.py`; 빔 `beam_native.py`, `beam_mesh_binding.py`, `beam_deck.py`, `beam_results.py` 확장. native에서 편집한 곡면/요소별 법선·두께·offset과 단면 방향, 회전·단면 응력·지지 합력 모멘트를 정확히 연결 | planar S8/B32R 예제를 넘어 추가 선언한 요소·형상 경로가 입력·결과·재편집까지 연결. 상하면 복원 응력과 적분점 원값, 절점 회전과 유도 회전을 구별. 모호한 재번호 대응은 차단 |
| B1.4 복합재·초기장·연결요소·체결 | E3 적층 순서/재료축/두께와 층별 결과, E4 온도·초기 응력/변형·면압/분포하중, E5 병진·회전 spring/damper, E6 bolt cut/axis와 체결력 또는 체결 변위의 tighten→hold→load. `analysis_conditions.py`, `fem_edit.py`, freeze/deck 접점에 도메인 helper 추가 | 적층 순서/축 변경이 실제 입력과 층별 응답에 반영. pressure×면적의 합력, spring/damper 방향·단위, 체결 후 본하중 상태 연속성 확인. 토크를 근거 없이 체결력으로 바꾸지 않음 |
| B1.5 접촉/구속 C1–C6 | `contact.py`, `contact_deck.py`, `contact_steps.py`, `adapters/tie_adjustment.py` 확장. hard 비관입, implicit cohesive, 곡면/경계/연쇄 tie 조정, small/large sliding, 단계별 접촉·tie 활성/해제, 병진/회전 주기 대응 | 각 기능이 실제 backend formulation/card와 일치. 큰 penalty를 hard로 이름만 변경하지 않음. A→B→C 조정은 순서·상류 변경 반영, cycle/모호 대응 차단. 주기 구속은 접촉 메뉴가 아닌 BC로 편집 |
| B1.6 접촉 응답·비선형 조합 | `adapters/contact_results.py`, `contact_inspection.py`, `calculix_material.py`, `calculix_controls.py`, `calculix_convergence.py`, 기존 Code_Aster adapter를 확장. pair별 pressure/gap/slip/status/force, 기준점에 대한 합모멘트, 재료·기하·접촉 조합의 실제 admission | 공유 절점의 pair 혼동·양면 이중 합산 없음. 실패 increment의 원설정·실제 수렴값을 열어 수정. J2+기하+접촉과 추가 재료/솔버 경로는 각각 검증한 범위만 Run 가능 |

B1.1은 `PoseCandidates._prepare`의 준비 generator와 `validate_model`의 재열기 검사에서 같은 형상 비교 규칙을 사용한다. `occurrence_fem.element_pairs`의 native history 대응은 재사용 근거지만, 그 함수의 평면/두 부품 등 기존 admission을 M4 전체에 그대로 적용하지 않는다. 저장 후 포인터 동일성만으로 부품 대응을 판정하지 않는다.

**M4 교정의 한계:** Solid와 Binder Compound의 outer Placement/BREP가 다르다는 이유로 같은 세계 형상을 거절하는 것은 오류다. 반대로 bbox·중심·체적만 맞는다는 이유로 통과시키는 것도 오류다. 원본 identity 검사는 유지하고, 비교 대상의 rigid transform을 한 번만 적용해 native topology/geometry와 orientation을 확인한다. 다른 위치의 반복 부품, 내부 형상이 다른 등체적 부품, 참조가 바뀐 부품은 계속 거절해야 한다. 준비 중 실패한 사본은 진단과 함께 보존하되 READY로 표시하지 않는다.

**소유:** 현재 M4 교정은 기존 Codex/Sol 담당에게 유지한다. B1.2–B1.6의 의미 있는 물리/모델 확장은 Pro 주작성, native 전용 패널은 계약 확정 후 Sol, 형상 동일성·접촉/체결 의미는 Astra 독립 검토다. 공통 명령·등록·저장 접점은 Codex가 별도 통합한다. 이미 진행 중인 shell/beam 파일을 다른 담당에게 중복 배정하지 않는다.

**의존·입출력:** M4 준비는 저장 자세와 native CAD만 필요하다. 구조 실행은 그 모델의 현재 mesh·재료·조건·단계 snapshot을 받으며 frozen input/실제 결과를 낸다. M1 일반 관계의 나머지를 전부 끝내야 기존 검증 frame의 M4를 인도할 수 있는 것은 아니다. B2는 B1의 단계/재료 계약을 재사용하고 B3는 결과를 소비한다. E3/E6, hard/cohesive의 solver 선택은 B4/B6와 맞추되 다른 정적 기능을 중단하지 않는다.

**검사 시점:** M4는 기존 실패 입력에서 준비·수정·저장/재열기 한 경로와 참조/자세 변조 거절을 확인한다. 새 요소·법칙은 작은 독립 기준 한 묶음으로 입력→실제 계산→결과 의미를 확인한다. 예를 들어 셸/빔 굽힘, 적층 방향 교체, spring/damper 부호, 체결력 평형, tie 조정 순서, 접촉 합력과 pair 귀속이다. 변경하지 않은 모든 solver benchmark를 다시 돌리지 않는다.

**종료:** B1 첫 인도는 기존 solid·shell·beam 왕복과 M4 편집 모델을 사용자가 끝낼 수 있을 때 게시한다. B1 전체와 FN-12/14/15 부모 행은 E3–E6, C1–C6, 결과 채널, 필요한 비선형 조합 및 B2의 교차 기여가 남아 있으면 닫지 않는다. 지원되지 않는 필수 기능을 ‘미지원 표시 구현’으로 완료 처리하지 않는다.

**SPEC:** `SPEC-PREFE-001` AC-01–15의 해당 CAD/기구/요소/접촉/비선형/Runner 조건, plan의 M1–M4·E1–E6·C1–C6·R1/R2·NS1/S2; `SPEC-CAD-NUMERICAL-001`, `SPEC-CONTACT-001`. 부록의 원 AC-D 매핑에 이 도메인 AC를 추가 연결한다.

## 4. B2 — 동역학·충격·손상 인도

**사용 순서:** 자기 solid/충격 모델 열기 → 초기 조건·단계·감쇠/접촉 설정 → 실제 계산 → 시간별 변위/속도/힘/에너지/손상 확인 → 조건 수정 또는 허용 restart → Post/Study에서 같은 결과 읽기 → 저장·재열기.

**현재와 새 작성의 경계:** `contact_steps.compile_program`에는 한 프로그램의 static 또는 dynamic 절차와 하중/변위 곡선이 있다. `render_steps`는 `*DYNAMIC`을 쓸 수 있지만, 프로그램 전체 procedure를 공유하고 동적 초기 변위를 0으로 제한한다. 이것은 NS2/N3 완성이 아니다. 이전 Pro NS2 ZIP은 재첨부 확인에서 실제 코드/패치가 없었다. 회수·적용 대기 대신 **현재 소스 기반 새 Pro 작성**으로 시작한다. 기존 동적 입출력·JobManager·Post와 충격 adapter는 재사용한다.

| 작업 | 구현 내용과 파일 | 인수 조건 |
|---|---|---|
| B2.1 NS2 초기 상태·시간 해석 | 단계별 procedure와 IC 데이터 확장. U[mm], V[mm/s], 밀도[Mg/mm³], 중력[mm/s²], Rayleigh α[1/s]/β[s] 등 선택한 감쇠 모델, 출력 시각/주기를 정의. `contact_steps.py`, `freeze_contact.py`, `contact_deck.py`, `contact_fem.py`와 새 `caelab/dynamic_conditions.py`/전용 패널 helper(신규 제안)에 연결 | 0이 아닌 U/V가 native 초기 조건에 들어가고 BC 충돌/중복·누락 밀도는 해당 대상에서 진단. 자유/감쇠 진동의 위상·주기·감쇠를 독립 기준 및 시간 간격 변화로 대조. 기존 정적 입력 불변 |
| B2.2 N3 정적→동적 | 한 연속 해석 안에서 정적 평형→본동적 단계 연결. 하중 유지/해제, 접촉 상태·소성/내부변수·변형 상태, step time/누적 물리 time/정적 load parameter 분리. initial condition 재지정과 상태 carry를 다른 명령으로 표시 | 정적 프리로드 상태에서 시작한 동적 응답이 연속 native 실행의 상태와 대응. 이전 정적 실패·불일치 model의 전달 차단. 변형 형상만 복사해 응력/내부상태 전달로 표시하지 않음 |
| B2.3 시간별 결과 | 기존 `frozen_fem.read_frd`, contact reader, `response_history/response_field`, Runner와 Post에 U/V·절점력·에너지 채널 추가. 필요하면 `caelab/adapters/dynamic_results.py`(신규 제안)로 parser/도출을 분리 | 원 시각/증분과 출력 간격 보존. A는 solver 원값과 V에서 구한 파생값을 구별하고 비균일 시각·양끝·gap 처리 명시. 원출력 없는 에너지는 미제공이며 임의 해석식으로 대체하지 않음 |
| B2.4 실제 restart | CalculiX `rout/rin` checkpoint의 보존·검사·새 attempt 입력 연결을 기존 jobs/owned execution 아래 추가. step/increment, solver build, native mesh/번호/재료/상태의 호환성을 검사. `caelab/adapters/calculix_restart.py`(신규 제안), 공통 job 접점은 integration 변경 | checkpoint 이후 이어 계산과 중단 없는 기준 계산이 같은 출력 시각에서 기존 수치 기준을 만족. 파일 누락/손상/모델 변경/호환 안 되는 build 거절. 처음부터 재실행·초기 U/V 복사·취소 접수는 restart가 아님 |
| B2.5 일반 충격 입력 | `impact_source.py`, `impact_model.py`, `impact_sets.py`, `impact_capture.py`, `impact_editor.py` 확장. INP PART/INSTANCE와 include, native RAD 입력을 각각 해석. 원 ID/변환 ID/instance 변환/재료·조건 대응 보존. rigid COM/관성/축, 측정 V/ω와 높이 유도 mode 구별 | 누락 card 없이 지원 부분을 명시 편집하고 실제 Starter→Engine→변환→Post. 원자료·편집본 분리, 반복 instance의 set 충돌 없음. 불완전 변환은 draft만 보존하고 Run 차단 |
| B2.6 충격 결과·손상·피로 | `impact_results.py`, `impact_responses.py`, `impact_damage.py`, `fatigue.py` 확장. pair별 접촉력, 실제 계산 증분의 충격량, 실패 자료 재후처리. LAW117 계면과 별도로 native 벌크 손상, 요소별 에너지, 재닫힘·재개구 이력. 다축/변형률 수명·평균응력 보정·반복 소성/계면 연계 | 힘 적분의 시각/샘플·단위와 질량/added mass/에너지 정의가 일치. 원 solver 실패 상태를 유지한 새 후처리 가능. 벌크와 계면 손상 독립 표시. 보정자료 없는 수명은 UNKNOWN, 한 cycle을 수명으로 표시하지 않음 |

**NS2 입력 구현의 선행 확인:** Pro는 설치된 CalculiX 버전의 실제 초기변위·속도·감쇠·출력·restart 카드와 소스 경로를 먼저 확인해 B2.1의 입력 모델에 연결한다. 지원하지 않는 초기변위 키워드를 만들거나, 무응력 형상 변경을 소성/프리로드 상태 전달로 대신하지 않는다. 저장 값→native 입력→첫 수락 상태의 대응을 작은 모델로 확인한 뒤 패널에 연결한다. 기존 밀도 읽기와 동적 단계 코드는 재사용하며 이를 통째로 미구현으로 세지 않는다.

**B2.6의 닫을 범위:** 먼저 기존 명시적 재료와 연결 가능한 native 벌크 손상 1종을 카드·출력·길이/에너지 정규화까지 선정해 구현하고, 추가 law 선택은 지원표에 명시한다. 계면은 opening→unloading→compression/reclosure→reopening과 mixed mode를 실제 지원 법칙으로 연결한다. 피로는 현재 단축 stress-life 외에 strain-life, 명시 평균응력 보정, 다축 이력의 선언된 평가법을 각각 실제 계산으로 인도한다. 알고리즘 이름만 추가하거나 필요한 교정계수를 기본값으로 생성하지 않는다. 이는 모든 재료의 수명 예측을 검증했다는 뜻이 아니다.

**중요한 restart 구분:** 일반 FCStd 재열기에서의 의미상 mesh 재번호 대응과 binary restart 호환은 다른 문제다. 빔의 기존 재번호 매핑이 성공해도 solver 상태 파일의 번호를 임의로 치환하지 않는다. 소유 프로세스가 종료됐는지 미확인인 경우 중복 continuation을 자동 제출하지 않는다. 마지막 수렴 checkpoint가 없으면 ‘새 실행’만 제시한다.

**소유·병행:** Pro-NS2가 B2.1–4의 핵심 작성, Pro-Impact가 B2.5–6의 입력/손상/결과 작성이다. 실제 Pro UI 동시 작업이 가능할 때 별도 대화·파일 범위로 분리하고, 한 대화만 가능한 때는 NS2 입력/상태 계약을 먼저 닫고 전환한다. Sol은 동적/충격 전용 패널과 원값 선택 연결을 맡는다. Astra는 시간·상태·restart·에너지/피로 의미를 독립 검토한다. `contact_steps/deck`, `frozen_fem.py`, 공통 job 변경은 Codex 순차 통합이며 동시 덮어쓰지 않는다.

**최소 검사·실패:** 기존 Windows native OpenCourant 경로를 유지한다. 새 NS2/N3는 작은 solid의 진동/프리로드 해제와 checkpoint 연속성, 충격은 작은 사용자 FE와 instance/단위 반례, 손상은 요소/계면 기준 및 필요한 mesh/time 비교, 피로는 알려진 cycle 이력으로 확인한다. 모든 실행에서 취소 접수·실제 종료·보존 prefix·후처리 실패를 분리한다. 실패 파서를 고친 뒤 원출력을 다시 읽는 데 솔버를 다시 실행하지 않는다.

**종료:** B2.1–4는 비영 IC·감쇠·상태 carry·필수 시간 응답·진짜 restart·저장/재열기가 모두 있어야 NS2/N3 인도 완료다. B2.5와 B2.6은 각각 별도 사용 인도로 게시하되 네 FN-16/17 행의 잔여는 끝까지 남긴다. 실제 Windows에서 WSL 없는 작은 계산을 확인하지 않았다면 native 인수는 미완료다.

**SPEC:** `SPEC-PREFE-001` NS2/N3와 E4/E5 및 비선형 실행 조건, `SPEC-IMPACT-001` REQ-IMPACT-001-001–008과 FN-16/17 acceptance, 접촉 응답은 `SPEC-CONTACT-001`과 연결한다.

## 5. B3 — 독립 Post·측정·비교·응답 반환

**현재 재사용:** `analysis.py`, `workspace.py`, `external.py`, `measurements.py`, `comparison_native.py`, `curve_native.py`, `source_repair.py`와 Qt Post. 지원 scalar 동일 mesh/선형 tetra 비교, VTU/PVD 재연결, 단위/기저·곡선 비교가 이미 있다. FN-27-01은 미구현이 아니라 전체 3D–표–곡선 조작 대조가 보류된 행이다.

| 작업 | 실제 개발/대조 | 종료 조건 |
|---|---|---|
| B3.1 선택과 닫기 | `native_controls.py`, `commands.py`, `bridge.py`의 관리 저장 관문에 File→Exit를 연결. `post_window.py`, native selection/measurement가 같은 source/field/association/component/time/point를 유지하는지 실제 대조 | Ctrl+S, X/Alt+F4, File→Exit의 저장/취소/실패 의미 일치. 3D 점·표 행·곡선과 원자료 열기가 같은 선택. 실패한 저장 뒤 창/초안 유지 |
| B3.2 비교 변환의 잔여 | 기존 `post_comparison.py`, native 비교/곡선 editor 확장. 단위 → 물리 측도 → 기저 → 시간 → 공간/association → 선택 성분/차이의 의존 관계를 검증해 실행. 각 변환의 입력·출력/지원범위 표시 | 원 A/B, 변환 B, B−A를 나란히 추적. 벡터에 위치 translation을 더하지 않음. tensor 성분 순서/shear 규약 보존. F/J 등 필수 정보 없는 finite-strain 측도 변환은 종속 비교만 차단 |
| B3.3 측정의 재사용 | `measurements.py`, `post_numerical.py`, `post_observation.py`, `post_measurement_dialog.py`와 기존 CAD/Plan 연결 확장/대조. 점·경로·면 평균·두 점 gauge 정의의 지원 범위를 실제 reader와 맞춤 | 실험 자료와 동일 gauge/방향/시각/단위. 강체 병진에서 gauge 신장 0. 새 설계에서 동일 물리 측정으로 평가하거나 참조 복구 요구. 선택만으로 계산하지 않음 |
| B3.4 복구·보고 반환 | 기존 source repair/new-branch와 `report_selection.py` 연결. input 이동/내용 변경, pipeline 적용 전 draft, 시간 channel 누락을 구별 | 같은 내용 재연결은 입력 의미 보존, 다른 내용은 새 branch. 옛 결과/분석 유지. 보고서/Study/Plan이 정확한 선택을 계산 없이 다시 엶 |

**독립 진입:** 외부 VTU/PVD와 기존 저장 결과로 먼저 인수한다. B1의 새 결과 ID는 연결 검사에만 필요하며 Post 개발의 선행이 아니다. 표본화는 선언한 시간 구간 안에서만, 공간 보간은 실제 지원 영역 안에서만 수행한다. delta mask와 percent mask(A≠0)를 구별하고 작은 ε로 0분모를 숨기지 않는다. association/좌표 정보가 없으면 진단과 원값은 남기고 해당 차분만 차단한다.

**소유:** 현재 File→Exit 담당 Sol 유지. 비교/측정 의미는 Pro, native/Qt 조작은 파일을 나눈 Sol, 공통 bridge/명령은 Codex 통합. B1/B2는 parser와 실제 field 의미를 공급하고 B3는 재해석 없이 소비한다.

**검사·종료:** solver 없이 제조된 상수/선형 field, 알려진 vector/tensor 회전, 시간 중간값·gap, 같은/다른 mesh, 0분모와 이동 파일을 사용한다. 실제 ParaView/Qt에서 선택→저장→취소/실패→새 프로세스 재열기를 확인한다. 외부 결과 단독 업무와 Pre/Numerical/Report 왕복이 모두 닫히면 B3 인도 완료다. 전체 reader 형식/모든 물리 측도 지원이라고 확대하지 않으며 FN-28-02의 명시 잔여는 남김없이 대조한다.

**SPEC:** `SPEC-POST-COMPARE-001` AC-PC-001–008 해당 시나리오, `SPEC-POST-NUMERICAL-001`, `SPEC-DESKTOP-001`의 독립 문서/저장 조건. 기존 FN-27/28 원행 종료 조건을 유지한다.

## 6. B4 — Data·Material의 시험 연구 인도

**사용 순서:** 단위·열 순서가 다른 시험 파일 열기 → 원행/채널·geometry·측도 지정 → 처리/품질 검토 → Material 시험 제어 선택 → 직접 평가 → 같은 Numerical Plan으로 다시험 fit/holdout → 임의 후보 상세/잔차 비교 → 명시 채택 → FE 할당 또는 Study → 저장·재열기.

**기존 구현:** `data_document.py`, `adapters/file_table.py`, `material_test.py`, Material owner, FELUPE/MFront adapters, `numerical.fit_model`, 원행 선택·mask·기존 피팅/holdout·명시 채택을 재사용한다. CSV import나 기존 두 계수 피팅을 새 기능으로 다시 세지 않는다.

| 작업 | 실제 남은 코드 | 끝낼 조건 |
|---|---|---|
| B4.1 처리 recipe | Data owner의 기존 mapping/row mask 위에 순서 있는 처리 정의, 단계별 미리보기·편집·재정렬·무효화·저장을 추가. `data_window.py`의 가상 표/선택을 유지하고 `caelab/data_processing.py`(신규 제안)에 순수 연산을 분리 | 단위 변환·선택 구간·지원 필터/재표본화 등 명시 연산의 순서가 실제 값에 반영. 원파일/NaN/gap/비단조 원행 보존. 큰 자료를 매 셀 편집마다 전부 로드하지 않음 |
| B4.2 유한변형 측도 | `material_test.column_mapping/measured_protocol`, 전용 test dialog 확장. A0/L0와 현재 A 또는 F/J, gauge/crosshead, 응력/변형률 측도·방향 입력. 단축·동축 시험에서 P11=F_axial/A0, σ11=(λ1/J)P11, e=ΔL/L0, lnλ의 유효조건을 분리 | 1250 μm→1.25 mm 등 숫자 변환과 원행 대응. J/현재 면적 없는 진응력 요청, λ≤0 로그는 차단. invalid 원문 draft는 저장. J=1을 자동 가정하지 않음 |
| B4.3 실제 시험 제어 | FELUPE/MFront material-point adapter의 trial/committed state를 분리해 자유 횡수축, stress-control, 혼합 F/stress 성분 제어와 시계열을 추가. protocol metadata만 바꾸지 않음 | P22/P33 등 선택한 횡응력이 설정 tolerance를 만족. prescribed lateral F=1 결과와 구별. 실패 증분의 원입력·잔차·마지막 수락 상태 보존; 실패 trial이 다음 증분/후보를 오염하지 않음 |
| B4.4 후보 상세 보존 | `numerical.fit_model`, `candidate_results_window.py`, `data_comparison.py`에 후보별 원입력/요약/실패/상세 ref와 명시 detail evaluation을 연결. 실행 전 retention policy를 고정 | 임의 후보 행 선택으로 실제 보존 곡선만 표시. NOT_RETAINED/NOT_EVALUATED는 그대로. 상세 추가 계산은 새 evaluation ID이며 옛 결과를 소급 채우지 않음 |
| B4.5 재료군·FE 전달 | 현재 J2 전달을 보존하고 압력 의존 DP의 명시 variant, 초탄성/점탄성 등 전체 명세의 재료군을 기존 law/interface 등록과 연결. Material model→적합한 FE card 또는 사용자 law interface, 필요 계수·measure·state를 명시 | 재료점 인장/압축/구속/제하와 해당 FE 시편에서 응력·변형·에너지/내부상태 대응. 미지원 pair만 export 차단. UI 목록·빌드 exit0가 아니라 실제 law/solver 조합으로 인수 |
| B4.6 기존 6행 완료 대조 | FN-03-01/04-01/04-03/07-01/07-03/09-02를 현재 코드와 연결. Data 품질∩operation-valid∩Plan inclusion을 원 sample ID로 고정하고 holdout 제외, multi-owner dirty와 target 변경/응답 유실을 확인 | 숨김과 통계 제외 독립. fit와 holdout 원행 겹침 없음. Material r17 결과를 r18에 silent overwrite하지 않음. 지원 law/solver의 기존 기준을 변화 없이 적용 |

**B4.3의 잔차 계약:** prescribed F 성분은 입력값으로 고정하고, 지정 stress 성분의 target−actual을 미지 성분에 대한 잔차로 푼다. 응력 측도·좌표계·독립 성분·단위와 tolerance를 protocol에 저장한다. 매 trial은 같은 마지막 수락 state에서 시작하고, 내부 수렴을 확인한 증분만 commit한다. solver 실패를 건너뛰어 이후 시간의 정상 곡선으로 잇지 않는다.

**B4.5의 제품 판단:** J2와 DP를 비교하는 원 사례 A를 삭제하지 않는다. 첫 DP는 선형 압력 의존 항복면, 명시 유동/팽창 및 경화 규약을 가진 하나의 variant로 설계·등록한다. 이는 모든 DP 변형을 지원한다는 약속이 아니라 실제 선택 가능한 법칙의 정의다. 실제 구현 backend와 계수 규약은 B6의 interface 작업 및 B1의 비선형 FE와 동시에 확정한다. 인장 자료만으로 압력 의존 계수를 식별했다고 주장하지 않고 압축/구속 holdout을 포함한다.

**입출력·실패:** Data는 raw와 recipe/quality, Material은 law/current values/protocol, Plan은 시작값/범위/weight/train/holdout을 소유한다. 응답 원단위의 잔차와 무차원 scaled objective를 따로 저장한다. 누락된 필수 예측 구간을 제거해 유리한 목적값을 만들지 않는다. 취소된 fit는 보존 후보를 읽을 수 있지만 선택/채택은 실제 존재하는 결과만 사용한다.

**소유·의존:** Pro가 processing·measure·mixed-control·retention/law 핵심 작성. Sol은 Data/Material 표·곡선·protocol editor. B5가 소유한 `numerical.py`와 B8의 공통 owner 변경은 사전 합의한 patch로 순차 반영한다. B6는 구성식 검사/FE interface, B1은 native 재료 할당을 담당한다. B8 전체 완료 전에도 기존 단일 owner 경로로 B4 인도 가능하다.

**최소 검사·종료:** 두 공개/합성 시험, loading/unloading 이력, 원행 mask/holdout 반례, 자유 횡수축과 구속 시험, retained/missing 후보, 채택 충돌·저장 실패를 확인한다. 추가 법칙/FE pair에만 독립 기준을 붙인다. 12행의 실제 추가 개발과 완료 대조를 모두 닫고 이 workflow를 새 프로세스에서 반복하면 B4 완료다. 실재 사용자 재료의 적합성 승인은 별도다.

**SPEC 연결:** FN-03/04/06/07/09와 FUNCTION_SPEC C01–C04, 기존 `SPEC-DESKTOP-001`, fit/결과 반환은 `SPEC-NUMERICAL-001/002`, law/FE pair는 `SPEC-RESEARCH-003`의 법칙·interface·독립 사용 조건. **RESEARCH-003의 주 범위는 FN-08/18/19이므로 D5 전체를 그 SPEC 하나가 이미 포괄한다고 쓰지 않는다.** 기존 SPEC acceptance에 원 FN 링크를 보완하고 중복 신규 SPEC를 만들지 않는다.

## 7. B5 — Numerical 연구 인도

**사용 순서:** 저장 Material/PDE/CAD/Evaluation 또는 외부 평가기 선택 → 변수·응답·목적·제약·예산 편집 → 명시 계산 → 표/그래프의 같은 후보 비교 → 보존 결과 또는 명시 추가 평가 → 원 owner에 채택 제안/Study 반환 → 저장·재열기.

`RequestPlanWindow`, `NumericalDocuments`, `numerical.py`, 기존 SciPy/SALib/DE/LHS·UQ·RBF·epsilon-constraint 경로를 유지한다. 새 optimizer framework, LLM 후보 생성, 두 번째 scheduler를 만들지 않는다.

| 작업 | 실제 구현 위치와 내용 | 종료 조건 |
|---|---|---|
| B5.1 변수와 DOE | `_variables/_decode/run_doe`와 입력 binding 확장. integer/명시 discrete set/category/종속 변수, 허용 조합·단위·의존식의 topological 평가. `caelab/variable_domains.py`(신규 제안)와 native/Material/PDE binding 연결 | 연속 해를 단순 반올림한 값이 아니라 생성 단계부터 허용 후보. category는 실제 도메인 선택으로 전달. 종속 순환/불허 조합 진단. 복수 응답 표·분포·rank-deficient/실패 후보 보존 |
| B5.2 민감도·UQ | `sample_sensitivity/analyze_sensitivity`, `run_uq`, `probabilistic_analysis.py`, `numerical_methods.py` 확장. Sobol N/2N 등 설계별 비교, histogram bin 선택, 차원 있는 covariance, 추가 joint/copula | A/B/cross 순서와 원 표본 동일성 유지, 누락/재정렬 설계 차단. covariance의 단위는 변수 단위의 곱이며 correlation과 구별. 전체/성공/실패 분모, 조건부 통계·초과율을 저장/재열기 |
| B5.3 일반 역해석 | 기존 `fit_model`, request plan, identification UI를 일반 evaluator의 여러 시험·응답·관측 잔차/holdout에 연결. 물리 실패와 검색 penalty 분리 | same-mask residual과 feasible 최적 후보를 선택. 목적·제약·실패/미평가를 별도 표시. 상세 추가 평가는 B4의 동일 retention 계약 사용 |
| B5.4 gradient/adjoint | 기존 Evaluation/domain descriptor에 지원 미분량·변수·상태·단위와 해당 방법 admission을 추가. 처음 실제 adjoint 경로는 B6의 선언된 PDE 한 경로, 그 외는 명시 유한차분/기존 derivative-free | 같은 시작 상태의 독립 perturbation과 방향미분/Taylor 검사를 통과. 유한차분을 adjoint로 표시하지 않음. 미지원이면 선택 방법만 unavailable이고 기존 search는 유지 |
| B5.5 국소 대리모델 | `surrogate_archive.py`, `fit_surrogate`, 후보 결과창 확장. 전역 RBF 계수 archive와 국소 neighbors 모델의 저장 계약을 구분. training data/지원영역/변수 순서/이웃 규칙·설정·보존 예측을 안전한 숫자 형식으로 저장 | 재열기와 보존 예측 열람은 fit/predict 0회. 새 점 예측은 명시 작업. 국소 계수 계산이 필요한 방법이면 그 실행 의미를 표시하고 새 결과에 기록. 학습점/holdout 중복 거절과 실제 계산 확인 유지 |
| B5.6 과거 학습 모델·다목적·MDO | 과거 surrogate 결과의 평가 모델 재선택을 검증된 참조와 연결. 3개 이상 목적의 축 선택/parallel-coordinate 또는 표 비교, 전체 차원의 Pareto 판정. 반복 Evaluation의 공유 변수·수렴 결과를 기존 탐색에 연결 | 그림 두 축 변경이 Pareto 집합을 바꾸지 않음. 재선택한 실제 모델의 단위/응답/변수 의미 차이를 명시. MDO의 미수렴/중단 결과는 유효 목적값이 아니며 후보 간 state 격리 |

**국소 RBF의 구체적 제약:** 현 `surrogate_archive.py`는 전역 계수를 저장하며 neighbors 방식은 명시 제외한다. 단순히 그 금지를 지우고 같은 archive로 복원하면 안 된다. 국소 예측 시 수행하는 계산과 새 학습을 구별하는 별도 kind/version을 기존 archive 안에서 정의한다. 새 점에 필요한 계산은 Predict라는 명시 행동에서만 수행하고, 재열기에 숨겨 넣지 않는다. 저장된 기존 예측을 여는 데 계산이 필요하다면 이 인수 조건을 통과하지 못한다.

**소유·의존:** Pro가 알고리즘 binding/retention/미분 계약, Sol이 방법별 표·그래프·선택 GUI, Astra가 표본·분모·미분·feasibility 의미를 검토한다. B5.1/2/3/5/6의 표시 부분은 작은 기존 평가기로 먼저 인도한다. B5.4의 실제 adjoint와 반복 MDO만 B6 해당 capability에 의존하며 D6 전체를 D7의 선행조건으로 걸지 않는다.

**검사·종료:** 정수·범주·종속 반례, known algebraic evaluator, 누락 Sobol block, PSD/covariance와 재정렬, fit/holdout overlap, local-model 재열기 무계산, 세 목적에서 두 축 투영으로 달라지는 반례를 사용한다. 실제 PDE 미분과 MDO에는 해당 작은 경로만 계산한다. 11행의 기능·반환·저장/실패 동작이 닫혀야 B5 전체 완료이며 기존 DOE 성공만으로 대체하지 않는다.

**SPEC:** `SPEC-NUMERICAL-001`, `SPEC-NUMERICAL-002` AC-NUMERICAL-002-001–009, CAD 후보는 `SPEC-CAD-NUMERICAL-001`, Post 관측은 `SPEC-POST-NUMERICAL-001`, 반복 평가 계약은 `SPEC-RESEARCH-003`.

## 8. B6 — 구성식·PDE·실제 장 전달 인도

**사용 순서:** Material의 법칙/구성 결과 또는 PDE 문서 직접 열기 → 상태/식/BC·IC·단위 편집 → 명시 평가 → 증분/field/같은 norm의 기준 비교 → 필요한 단계와 전달을 Evaluation에서 편집 → 단독 실행 또는 같은 저장 정의를 Numerical에 전달 → Post/Study → 저장·재열기.

| 작업 | 구현/대조할 코드 | 종료 조건 |
|---|---|---|
| B6.1 구성식 검사·interface | `constitutive_inspection.py`, `constitutive_inspection_window.py`, `user_material.py`, `adapters/user_mfront.py`, MFront/FELUPE adapters 확장. 상태/응력·변형/접선의 measure·frame·성분과 native build/interface를 연결 | 같은 초기 상태로 복원한 perturbation과 정의가 같은 tangent pair 비교. B4 추가 법칙을 실제 FE interface로 export/실행. 컴파일 성공·point integration·FE 사용을 각각 구별 |
| B6.2 독립 식 연구 | `pde_document.py`, `dimensioned_expression.py`, `dimensioned_models.py`, `adapters/dimensioned_ode.py`, `dimensioned_weak.py`, 기존 nonlinear/transient/vector/imported PDE adapters와 `pde_window.py` 대조·누락 수정 | 식·상태/차원·영역·공간·BC/IC 변경이 실제 선택 adapter 입력에 반영. invalid AST/차원 draft 저장, 식 Check는 계산하지 않음. 같은 오차 norm·기준·mesh/increment 비교와 Post/재열기 |
| B6.3 실제 mapping | `evaluation_definition.py`, `transfer_inspection.py`, `physical_fields.py`, 기존 field 전송 구현을 확장. 다른 mesh/시간/단위·basis 대응, 필요한 mask·보존 원값과 receiver 값 표시 | 상수/선형 field를 서로 다른 mesh에 전달해 독립값 대조. 필수 receiver 영역이 무효면 solve 차단. K와 ΔT, 구조 소유 Tref가 한 번만 반영. interpolation/conservative transfer를 다른 capability로 표시 |
| B6.4 반복 연성·재사용 | 기존 `execute`, stage attempts, lag/iteration와 restart-safe prefix를 대조·보완. B5용 공유 변수/미분 descriptor와 반복 residual 전달 | 물리 시간 시작 state에서 각 trial을 시작하고 수렴 단계만 commit. 최대 반복/실패/취소 원값 보존. 같은 정의·입력의 허용 prefix만 명시 재사용. 같은 문서 직접 실행과 Plan 참조의 결과 정의 동일 |

**Windows 결정:** `pde.scipy.ode`는 기존 Windows 우선 계산 경로로 유지한다. 기존 FEniCSx 약형식·MGIS/MFront의 Ubuntu 실제 결과를 Windows native 성공으로 옮기지 않는다. B6.2는 현재 선언된 일반식 범위의 완료 대조이지 이미 있는 ODE/weak editor를 새로 만드는 작업이 아니다.

도구의 편집·저장·보존 결과 읽기와 Windows 지원 ODE/Material 계산은 Linux/WSL 존재와 무관하게 인수한다. Linux 전용 capability는 이미 사용 가능한 경우에만 명시 선택한 기존 Linux/원격 runtime으로 분리하며 Windows 사용자에게 WSL 설치를 자동 요구하지 않는다. 필요한 FE/PDE 기능의 Windows 배포 공백은 **Luna의 해당 runtime 소스/무료 배포 확인 → Pro의 기존 adapter/worker Windows 이식 또는 호환되는 기존 OSS backend 선택 → Codex의 실제 Windows 실행** 순으로 해당 기능 안에서 처리한다. 이 선택은 인터페이스·방정식·기준을 바꾼다면 별도 capability로 추가해야 하며 dimensionless 결과의 이름만 바꾸는 대체는 금지한다. 실제 대체 경로를 만들지 못한 필수 항목은 열린 개발 항목이지 ‘미지원 안내 완료’가 아니다.

**B6.3의 첫 대상과 확장:** 먼저 기존 P1 온도 field의 다른 mesh 전달과 시각 대응을 닫는다. 이어 벡터/텐서·association 변환은 B3의 검증된 수치 변환 코드를 재사용하되 열량/하중처럼 보존이 필요한 port는 보존 오차를 별도로 검사한다. 단순 nodal interpolation을 conservative transfer라고 부르지 않는다. 열–구조–계면 사례 C의 실제 온도·변형·계면 응답은 B1/B2와 연결한다.

**소유·의존:** Pro가 law/interface·식/전달/반복 계약, Sol이 inspector·equation/transfer editor를 맡고 Astra가 state·단위·mapping·수렴을 검토한다. `evaluation_definition.py`의 반복 실행과 B5 MDO는 같은 소유자가 관리한다. B5의 일반 변수/참조 계약만 먼저 합의하고 전체 Numerical 완료를 기다리지 않는다.

**검사·종료:** 기존 법칙별 tangent 기준, 실제 ODE/weak/nonlinear 등 선언 모델별 기준과 저장 경로를 연결한다. 새 mapping/iteration만 작은 제조 field와 free thermal expansion/이중층 기준으로 추가 검사한다. 전송 실패가 receiver Run을 막고 producer 결과는 읽히는지 확인한다. 7행의 실제 추가 개발과 완료 대조를 끝내야 B6 전체를 닫는다. 실행 환경별 지원과 실제 확인은 분리한다.

**SPEC:** `SPEC-RESEARCH-003` REQ-RESEARCH-003-001–008 및 FN-08/18/19 acceptance. 기존 plan의 ‘D6 인도가 끝난 실제 통합 버전’은 필요한 공통 코드 기준을 뜻하도록 한정하고, D6 전체 완료를 새 선행조건으로 확대하지 않는다. WSL 우선 실행 서술은 위의 Windows 독립 조건으로 수정한다.

## 9. B7 — Study·Expert·실험·보고서 인도

**사용 순서:** Study 또는 자료/결과에서 질문 작성 → 경쟁 가설·문헌/계산 근거 선택 → 필요할 때 실제 Expert 논의 → 편집 가능한 Plan 실행 → 같은 결과로 후속 논의 → 실측과 비교해 판단 또는 보류 → 다음 시험/설계 기록 → 보고서 편집·출력·재열기.

| 작업 | 구현/대조할 코드 | 종료 조건 |
|---|---|---|
| B7.1 문헌과 판단 | `assist/knowledge.py::KnowledgeStore`, `study_document.py`, `study_window.py`, reference picker 확장. 기존 source/segment/locator를 선택해 Study에 연결하고 변경/누락 표시 | Study가 Expert 없이 질문·가설·판단·다음 행동을 저장. 문헌 원문 위치를 열고, 새 자료가 옛 판단을 자동 변경하지 않음. URL만으로 검증 표시하지 않음 |
| B7.2 실제 Expert 왕복 | `expert_window.py`, `discussion_view.py`, `discussion_costorm.py`, `assist/costorm.py`, `expert_connection.py`, `result_return.py` 기존 경로 대조·UI 누락 수정 | 실제 선택 provider의 발언·인용·reply 대상·부분 응답·pause/resume·사용자 개입 보존. 같은 Plan/result를 현재 원 토론/Study에 명시 Attach. 응답 유실 재시도에서 이미 끝난 turn 중복 없음 |
| B7.3 불확실성·계측 대응 | `experiment_calibration.py`, `experiment_dialogs.py`, `data_comparison.py`와 B3 측정을 확장. 제공 표준/확장 불확실성·단위·포함인자·상관, 교정식과 gauge/time의 전파 | 원행/원값/보정값/전파값과 비교 결과 재열기. 선형은 독립 식, 비선형은 명시 민감도 또는 수치 전파로 확인. 미제공 불확실성을 0 또는 독립 가정으로 채우지 않음 |
| B7.4 식별성과 다음 시험 | `identification.py`, `identification_window.py`, B5의 실제 fit/DOE 잔차를 연결. robust/DE 결과에도 별도 perturbation/profile 또는 명시 표본 분석을 수행 | optimizer 성공·작은 잔차·국소 SVD를 전역 유일성으로 부르지 않음. 식별 가능/고정/미식별 계수와 이를 가르는 다음 시험을 정확한 결과에 연결 |
| B7.5 3D 보고 | `report_document.py`, `report_selection.py`, `report_pages.py`, `report_window.py`에 native Post의 선택 field/time/camera/filter/legend 이미지를 명시 capture하는 연결 추가 | 보고서 섹션 편집·Undo·정렬·미리보기·PDF/MD export. 보고 frame은 나중 원창 변경에 따라 바뀌지 않음. 이미지 원결과 위치를 열 수 있고 누락/실패/UNKNOWN/NOT_RELEASED 보존 |
| B7.6 실장비 | 기존 Data acquisition 설정과 실행 수명을 재사용해 `caelab/device_acquisition.py` 및 선택 장비 adapter(신규 제안) 추가. 채널·timestamp/sequence·overflow·calibration·연결·물리 stop acknowledgment 분리 | 실제 허가 장비로 취득→끊김→재연결→물리 stop 확인→같은 raw 자료 저장/재열기. 파일 replay를 live 취득으로 표시하지 않음 |

**실장비의 외부 입력:** 장비 모델·통신 protocol/driver·접근 권한·교정 자료·허용 동작·물리 stop 기준이 첨부에 없다. 이 값이 없어도 파일 수집 설정, sample/sequence 보존, 오류/종료 상태 UI와 adapter 경계는 작성한다. 실제 장비 binding과 물리 인수는 이 행에만 ‘외부 입력 필요’로 남긴다. 이를 사용자에게 모든 개발을 멈추고 선택하라는 질문으로 돌리지 않는다.

**Expert 비용·연결:** 첨부에는 기존 구독/OAuth의 실제 응답과 Co-STORM source→report 실행 기록이 있다. ‘provider를 아직 전혀 못 붙임’으로 다시 계획하지 않는다. 현재 선택한 경로의 인증/한도는 실행 시 실제 확인하고, 없는 경우 draft·보존 토론·보고 읽기는 유지한다. 추가 유료 API·새 구독·자동 공급자/모델 전환은 금지한다. 개발용 Pro 작업과 제품 Expert inference를 구별한다.

**소유·검사·종료:** Pro가 knowledge/판단·불확실성/식별·취득 의미와 report capture 계약을 작성하고 Sol이 전용 GUI를 맡는다. 기존 실제 로그인 경로를 무조건 반복 호출하지 않고, 바뀐 대화/재개 경로가 요구하는 제한된 실제 round만 확인한다. 단위/계측은 작은 합성 자료, 보고서는 보존된 3D 결과로 검사한다. B7.1–5의 독립/왕복 사용을 먼저 게시하고 B7.6 실제 장비 미확인은 분명히 남긴다. 그 상태에서 FN-35-01이나 전체 9행 완료를 주장하지 않는다.

**SPEC:** `SPEC-EXPERT-001/002` E1–E10/acceptance, `SPEC-EXPERIMENT-001` AC-EXPERIMENT-001-01–06와 실제 장비 조건, FN-29/30/05/32/35. 기존 knowledge 참조를 별도 문헌 시스템으로 복제하지 않는다.

## 10. B8 — 일상 사용·공통 연결·배포 인도

B8은 마지막에 시작하는 묶음이 아니다. 모든 인도에 필요한 연결을 먼저 제공하고, 전체 이동/배포/원격 확인을 마지막에 닫는 수평 작업이다. 기존 독립 시작 메뉴·launcher·owner·service를 재사용하며 기본 웹 화면으로 되돌리지 않는다. 내부 loopback transport와 웹 제품 화면을 혼동하지 않는다.

| 작업 | 실제 구현과 파일 | 종료 조건 |
|---|---|---|
| B8.1 정확한 열기·최근 문서 | `apps/research/desktop.py`, `desktop_links.py`, `workbench_client.py`, native startup 연결 대조. store/document/native host 식별과 recent/file-type 진입 | 같은 store/doc는 기존 창 활성화, 다른 store는 구별. native 원문서·원결과로 직접 열리고 새 실행 없음. 선택되지 않은 사용자 창/서비스 변경 없음 |
| B8.2 복수 owner 편집·저장 | 기존 base owner/창의 command/CAS를 재사용. `apps/research/multi_owner_edit.py`, `apps/research/related_save.py`(신규 제안)에 UI 조정/저장 receipt를 두고 실제 저장은 각 owner가 수행 | Enter/Esc/F2/Undo와 다중 열 paste가 의도한 owner만 변경. Material 저장 성공·Plan 실패를 부분 성공으로 표시하고 옛 Plan ref·dirty buffer 유지. 실패 owner만 명시 재시도 |
| B8.3 이동용 사본 | 기존 storage/registration/native project dependency를 순회해 staged copy, dependency 검사, 새 store/document ID와 derived_from, 마지막 manifest 게시. `caelab/portable_branch.py`(신규 제안) | 원 store 접근을 끊은 새 프로세스에서 연구 문서·FCStd·Post·보존 결과 열기. 한글/공백 경로, 중단/용량 부족 시 원본 불변. 타 PC 바이너리 경로·credential은 복사하지 않고 선택 runtime 재확인 |
| B8.4 외부/원격 실행 | `numerical.export_batch/import_batch`, `adapters/external_files.py` 기존 후보 교환 대조. 기존 JobManager 아래 `caelab/remote_execution.py`, `caelab/remote_schedulers.py`(신규 제안)로 SSH 실행과 Slurm/PBS 제출/조회/취소/회수 경계 추가. 실행 명세와 자원/환경을 구별 | 후보값 변경·duplicate/stale/missing 결과를 원 후보와 대조. 응답 유실/재접속 시 scheduler job ID를 조회해 중복 submit 없음. 실제 종료 확인 후 파일 회수·검사. 원격 미확인은 로컬 실행을 막지 않음 |
| B8.5 선택적 연결 보기 | `reference_window.py`, `research_context.py`, `desktop_links.py`와 같은 저장 refs 위에 `apps/research/reference_graph.py`(신규 제안)의 graph view 추가 | 그래프 drag와 목록/메뉴/키보드가 같은 명령. broken reference와 new revision을 구별. Workbench 없이도 모든 독립 도구 사용 가능 |
| B8.6 설치·동등 명령 | 현재 기록의 Windows 시작·설치 scripts와 ZIP에 있는 `openscience/workbench_mcp.py`, CLI/Python wrappers 연결 대조. 시작 scripts는 실제 checkout의 경로·내용부터 확인 | 새 Windows 환경의 시작 메뉴/지원 파일 더블클릭·같은 service/store·한글 경로. GUI/CLI/Python/MCP가 동일 target/value/result/error. 라이선스·등록 지원·설치 probe·실제 인수를 별도 표시 |

**원격의 외부 입력:** 첨부에서 일반 SSH/Slurm/PBS 제품 구현은 확인되지 않았다. 기존 승인 호스트, scheduler 종류/queue/account, 작업 경로·전송 권한·설치 runtime이 실제 첫 연결의 입력이다. Pro가 공통 실행/회수 프로토콜과 scheduler adapter를 작성하고, 실제 사용 가능한 첫 조합을 Codex가 연결한다. 다른 scheduler에 같은 성공을 전파하지 않는다. 호스트가 없다면 adapter와 모의 실패 검사는 인도하되 live 제출/중지/재연결은 미확인으로 남긴다. 새 유료 서버를 조달하지 않는다.

**소유:** Codex는 공통 core/schema/registration/transport/lifecycle와 Windows scripts를 단독 통합한다. Pro가 B8의 portable/related-save/remote 등 의미 있는 기능의 원안을 작성하며 Codex는 그 저작을 대신했다고 표시하지 않는다. Sol은 bounded 창/메뉴/graph. `MaterialDocuments`처럼 다른 owner의 기반이 되는 파일은 domain 담당자가 각각 직접 덮어쓰지 않고 integration patch로 반영한다.

**검사·종료:** 두 실제 client의 stale/BUSY_EDIT/응답 유실, related-save 실패, 원 store 없는 이동 사본, native 두 host의 명시 target, 새 Windows 시작과 WSL 없는 지원 계산을 확인한다. 별도 test store와 test-owned process만 사용한다. first-launch version 감지나 shortcut 생성만으로 FN-33 전체를 닫지 않는다. B8의 11행 대조와 실제 개발을 끝내고 외부 환경 조건을 분리해 배포 인도한다.

**SPEC:** `SPEC-DESKTOP-001` AC-D 조건, `SPEC-DESKTOP-002` AC-D02-01–06, 원 FN-01/02/26/31/33/34. 원격은 기존 Numerical/Runner 수명 계약 안의 확장으로 관리한다.

## 11. 병렬 작성·파일 소유·순차 통합

### 11.1 실제 역할과 동시 작업량

처음부터 13슬롯을 채우지 않는다. 현재 활성 작업을 재사용한 뒤 **Codex 서브에이전트 6개 수준**으로 시작한다: Sol native 연결, Sol Post, Sol Research GUI, Astra 핵심 독립 검토, Luna 코드/원행 대조, Luna runtime/MoAI 조사다. 대형 parser/물리 검토가 겹칠 때만 검토·탐색 슬롯을 추가해 8개 안팎으로 운용하며 실제 상한 13을 넘지 않는다. 주 Codex와 실제 Pro UI 작업은 이 숫자의 기능 대체물이 아니다. 활성 슬롯의 정확한 계수 방식은 현재 Codex 런타임에서 확인한다.

Pro는 의미 있는 기능의 주작성자다. 첫 새 작성은 NS2/N3와 Data·Material이며, 이어 Numerical 고급 기능과 구성식/전달, 충격/손상 및 portable/remote 핵심을 실제 Pro 대화에 작업 단위로 배정한다. 동시 Pro UI가 준비되지 않았다는 이유로 Sol에게 핵심 저작을 몰래 바꾸지 않는다. 그동안 Sol은 이미 합의된 panel/연결, Luna는 필요한 자료, Codex는 현재 통합을 계속한다.

| 파일 경계 | 쓰기 책임 | 다른 담당자가 요청하는 방법 |
|---|---|---|
| 현재 M4 `assembly_pose_*` 및 현재 지정된 native 수정 | 현재 Codex/Sol의 소유 유지; 기능 확장은 해당 Pro와 합의 | 현재 미커밋 변경 먼저 대조. 되돌리거나 옛 main 파일로 덮지 않음 |
| 각 새 도메인 helper·parser·adapter | 배정된 Pro 한 명 | Sol은 명시 read/command 계약만 소비. Astra는 read-only finding |
| 각 전용 Qt/native panel | 배정된 Sol 또는 이미 소유한 Pro 한 명 | core 작성자가 같은 panel을 동시에 편집하지 않음. input/state/error contract 먼저 전달 |
| `caelab/numerical.py`·Plan compiler | B5 Pro 주작성, B4 변경은 합의한 함수 범위 patch | fit/retention patch 먼저 순차 적용한 통합 기준을 B5에 제공. 동일 파일 병렬 branch merge 기대 금지 |
| `contact_steps.py`/`contact_deck.py`/`freeze_contact.py`·공통 FRD | Codex 통합 소유; B1/B2 Pro가 기능 patch 작성 | 단계 스키마·출력 정의를 먼저 합의하고 구간별 순차 적용. parser 수정 후 소비자 갱신 |
| `evaluation_definition.py`·field transfer | B6 Pro 주작성 | B5의 MDO/gradient 요구를 이 파일의 두 번째 구현으로 만들지 않고 계약/patch로 반영 |
| 공통 `material_document.py`, schema/storage/registry, workbench/client, native transport, CLI/MCP/routes, desktop dispatch | Codex 단독 통합 | 기능마다 `integration.patch` 또는 같은 의미의 별도 commit으로 전달. Pro 핵심 구현 출처 유지 |
| CURRENT_STATE, SPEC 상태, 운영 문서·루트 설치 scripts | Codex | 담당자는 실제 변경·검사·사용법만 전달. 다른 작업 상태를 임의 갱신하지 않음 |

### 11.2 먼저 맞출 작은 인터페이스

I0에서 기존 이름을 유지한 다음 네 계약만 필요한 범위로 확정한다: 단계/IC/restart, field/측정/유효 mask, typed 변수/평가기·상태/미분, 여러 owner 저장/열기/ref. 새 schema를 전면 교체하는 절차가 아니다. 각 공급자는 기존 타입·필드와 추가 필드의 기본 해석, 오류 예시, 버전 호환을 한 작은 예제로 제공하고 소비자는 같은 예제를 바로 읽는다.

공급자와 소비자는 실제 Codex 메시지 도구 또는 접근 가능한 기존 공동 대화/Space에서 직접 질문한다. ‘어느 입력에서 어떤 값/상태가 필요하며 현재 무엇이 나오는가’를 구체적으로 교환한다. 실시간 공동 연결이 없는 Pro에는 Codex가 그 쟁점과 필요한 코드 구간만 전달한다. 접근하지 못한 대화를 읽었다고 가정하거나 모든 업무를 긴 대화 로그 회수로 바꾸지 않는다.

Astra의 finding은 원행/실제 코드/반례/기대 동작/최소 수정 범위로 작성한다. 작성자는 수용 또는 반박을 수치·계약으로 답한다. Codex가 공통 경계와 최신 요구에 맞춰 채택·기각·후속 범위를 결정한다. 데이터 손실·물리량 오해·중복 실행 위험은 해당 merge를 막지만 무관한 묶음은 계속한다. 취향·장비 권한·새 비용처럼 실제 사용자 결정이 필요한 사실만 사용자에게 돌린다.

### 11.3 루트 통합 지점

| 통합점 | 선행 입력 | Codex가 순차 반영할 것 | 통과 뒤 즉시 열 작업 |
|---|---|---|---|
| I0 현재 진행 보존·계약 | current 변경과 활성 파일 소유 | 필요한 additive 계약·read sample·작업 잠금. 기존 M4/Sol 계속 진행 | Pro/Sol의 독립 작성과 저장된 결과 기반 개발 |
| I1 첫 native 인도 | B1.1, 기존 solid/shell/beam, B3.1, B8 필수 열기 | common command/registry/native 메뉴·문서열기 | 사용자 Pre→Run→Post·M4 모델 편집 |
| I2 자료·연구 인도 | B4 core, B5 독립 분석, B7 문헌/보고 | 같은 Data/Material/Plan/Study 결과 참조·related-save 접점 | CSV→fit/holdout→채택 및 독립 Numerical |
| I3 상태·물리 전달 | B2 단계/출력/restart, B1 추가 물리, B6 mapping | 결과 descriptor·시간/상태·adapters·B3 소비 연결 | 정적→동적/충격, 장 전달과 비교 |
| I4 전체 인도 | B5 고급·B7·B8 이동/배포와 잔여 B1/B2 | migration/backward read·설치·문서/명령 parity | 모든 독립 진입과 종합 왕복 |

I1–I4는 장기 release train이 아니다. 관련 동작·저장·실패 처리가 닫힌 작은 사용자 인도는 해당 통합점 안에서 바로 게시한다. 적용 가능 코드·관련 최소 검사·공개 예제·짧은 한글 사용법을 함께 낸다. 기능 코드와 공통 연결을 분리해 받아 루트가 충돌 없이 반영하되 patch 파일의 존재 자체를 완료 조건으로 삼지 않는다.

## 12. MoAI와 실제 실행 도구를 작업에 붙이는 방법

**능력 구분:** 첨부의 현재 callable MoAI MCP는 `spec_audit`, `spec_drift`, `spec_progress`, `todo_list` 네 개다. CLI의 `agent/workflow`는 lint이며 Codex 병렬 실행 엔진이 아니다. 이 계획 작성 환경에서는 MoAI/Windows Codex 협업 호출을 수행하지 않았다. 다음은 해당 기능이 있는 실제 Codex 작업 환경에서 실행할 절차다. 호출 성공이나 서브에이전트 활동을 미리 기록하지 않는다.

첫 작업에서 현재 등록된 MoAI skill/CLI 경로와 help를 읽고 사용 가능한 하위 명령을 확인한다. `plan/run/sync`는 그 설치의 실제 스킬 절차로 사용하며 존재하지 않는 `/moai ...` 또는 MCP 메서드를 지어내지 않는다. 기존 기록에는 `todo next 3`와 `decision record` 사용이 있으나 과거 task 3을 이번 새 작업에 그대로 적용하지 않는다. 현재 `todo_list` 결과에서 기존 task와 원 FN/SPEC 대응을 먼저 찾는다.

| 도구/절차 | 목적·입력 | 산출물·실행 시점 | 사용할 수 없거나 결과가 불충분할 때 |
|---|---|---|---|
| plan 스킬 + MCP `spec_progress/todo_list` | 최신 74행, B1–B8, 실제 파일 소유와 현재 작업 | 기존 task에 실행 항목/owner/dependency를 연결. 묶음 착수 또는 실제 범위 변경 때 | 새 SPEC/중복 74행을 만들지 않고 이 인계와 기존 acceptance를 사용. 미호출 상태 명시 |
| MCP `spec_audit/spec_drift` | 해당 기존 SPEC, 현재 코드/통합 기준 | 누락 acceptance·오래된 상태·연결 불일치 후보. 착수와 인도 전 | 과거 `spec view` 추출 실패를 코드 미구현이나 PASS로 해석하지 않음. 원문과 실제 코드 수동 대조 |
| CLI todo | 현재 task ID와 원 FN, 다음 사용자 인도 작업 | 담당/진행/막힌 입력/완료 상태. 배정·인도 때만 갱신 | 문법은 설치 help 기준. 로컬 기록/현재 표와 모순 없이 유지. todo 완료가 제품 인수는 아님 |
| CLI graph | 실제 의존성과 파일 공유 관계 | M4 전체→Post, D6 전체→D7 같은 잘못된 직렬 선행과 cycle 발견. I0/계약 변경 때 | 지원 import/schema가 없으면 파일/원행 의존표를 직접 대조; 그래프 생성 성공을 가장하지 않음 |
| CLI integration | 공급자/소비자 contract와 공통 파일 변경 | 인터페이스 불일치·소유 충돌·순차 통합 목록. I0 및 I1–I4 merge 직전 | 해당 명령이 없다면 같은 입력으로 Codex 통합 검토. 기능 코드 작성은 계속 |
| CLI decision | 실제 중요한 이견과 대안/선택/영향 | 예: restart 호환, hard/cohesive backend, 국소 RBF 저장, Windows 전용 runtime 경계. 결정 때 1회 | 사소한 문구·배치마다 ADR/새 결정을 만들지 않음 |
| run 스킬 + 실제 Codex 협업/Pro UI | 기존 코드·자기 파일·실행 가능한 작업 카드 | analyze→preserve→modify→focused test. Pro 핵심 코드와 Sol GUI를 병행, 실제 메시지로 쟁점 교환 | MoAI agent/workflow lint로 agent가 실행됐다고 하지 않음. 실제 UI 미연결은 명시하고 다른 작업 진행 |
| ast-grep | 바뀐 파일과 확인된 구조 규칙 | 공통 명령 우회, stale/session 누락, process cleanup 누락 등 변경 부위 검색. 수정 전후 | 과거 실행기/규칙 없음으로 NOT_RUN인 기록 유지. 설치된 무료 실행기 확인 전 scan 성공 주장 금지 |
| ast-edit | 안전한 작은 반복 수정과 위치 목록 | 순수 wrapper/명명 변경 등 제한된 edit; diff와 관련 test 확인 | 상태 전달·solver card·단위/파서는 구조 치환만으로 수정/검증하지 않음. 불명확하면 일반 코드 편집 |
| gate/LSP | 변경 module, 해당 호스트 Python/import 경로, 관련 tests | syntax/type/import/변경 영향 검사. 작은 commit·통합 직전 | 실제 gate/LSP가 있는 언어만 사용. FreeCAD/ParaView bundled imports를 일반 Python 오류와 구별. 미가동은 compile/관련 tests로 보완하고 별도 명시 |
| sync 스킬 | 구현물, 원 FN/AC, 실제 검사, 사용법 | 원행 상태·기존 SPEC/현재 상태·메뉴/예제·게시를 일치시킴. 사용자 인도 완료 때 | 문서 동기화/발행만으로 소프트웨어 완료나 native 인수를 선언하지 않음 |

개발 시작 전 모든 MoAI 도구를 억지로 한 번씩 돌리는 의식은 하지 않는다. 각 도구의 실제 목적과 산출물을 위의 작업에 붙인다. 기본 코딩·통합은 실제 Codex/Pro로 진행하며 도구 부재가 전체 승인 작업을 중단시키지 않는다. 필요한 무료 실행기 설치도 기존 환경·라이선스·허용 범위를 먼저 확인한다. 새 유료 모델·API 키·구독·서버는 도입하지 않는다.

## 13. 검사 시점과 명확한 종료 판정

### 13.1 개발 중 최소 확인

모든 작업 카드에 성공 경로, 그 기능의 대표 실패/취소, 저장·재열기 확인을 넣는다. 단순 Qt 문구/배치 수정은 해당 실제 창과 선택/초점만 확인한다. 물리량/solver card/parser/mapping이 바뀐 때만 그 의미를 검증하는 작은 수치 기준을 추가한다. 현재 실패 수치를 낮추거나 허용치를 바꿔 통과시키지 않는다.

native 테스트는 시작 시 test store, 자식 PID/handle과 소유 프로세스를 기록하고 `finally`/timeout cleanup으로 정상·실패·timeout 모두 정리한다. 테스트의 정리는 시험용 실행에만 적용하고 제품 사용자의 창 닫기와 job 취소는 기존 별개 계약을 유지한다. 프로세스 이름 전체 종료, 임의 PID 재부착, 사용자 FreeCAD/ParaView 창 종료는 금지한다. 정리 미확인은 별도 실패이며 새 실행을 자동 중복 제출하지 않는다.

### 13.2 묶음 인수

각 B의 workflow를 실제 도구에서 시작해 입력을 바꾸고 결과를 골라 다른 도구로 넘긴 뒤, 새 프로세스에서 같은 문서와 결과를 다시 연다. 한글·단위·table/curve/3D 선택, 중요한 Enter/Esc/Undo/Save/close를 실제 Windows에서 확인한다. 기존 1440×900/1920×1080와 기존 지정 DPI를 기준으로 하고 접근성 확대에서 주요 입력이 잘리는지만 추가 대조한다. offscreen 렌더와 실제 OS 입력 인수를 합치지 않는다.

**각 인도의 공통 끝 조건:** 지정 기능 코드와 실제 메뉴/명령이 연결되고, 원입력·단위·결과가 일치하고, 실패/취소/재열기에서 원본과 사용자 편집이 보존되며, 공개 소형 예제와 짧은 사용 순서가 게시돼 사용자가 직접 시작할 수 있어야 한다. 남은 부모 범위는 같은 원행에 적는다. 이를 통과한 인도를 다른 묶음의 미완료 때문에 보류하지 않는다.

### 13.3 최종 전체 연결 확인

| 통합 장면 | 실제로 닫을 왕복 | 완료를 막는 경우 |
|---|---|---|
| 구조·설계 | native CAD/조립→M4/FE→Run→Post 측정→Numerical 후보→명시 설계 변경→저장/재열기 | source 변경/잘못된 occurrence/옛 mesh 조건을 통과시킴, 후보가 원모델을 몰래 덮음 |
| 자료·재료·시험 | Data 원행→교정/처리→Material protocol→다시험 fit/holdout→선택 법칙 FE→실측 비교→Study→Report | 다른 측도·표본·gauge 사용, holdout 오염, 미보존 상세를 재계산 없이 있다고 표시 |
| PDE·다분야 | 사용자 식→실제 field→다른 mesh/time 전달→구조/계면→반복 평가→MDO→Post/판단 | Tref/단위 중복, 수렴하지 않은 field 사용, 후보/반복 state 누적 |
| 동역학·손상 | 정적 상태→동적/충격→checkpoint continuation 또는 명시 새 실행→힘/에너지/손상/피로→Post/Study | restart와 rerun 혼동, 실패 출력 누락, 없는 물성/에너지/수명 합성 |
| 독립·자동화·배포 | 각 도구 직접 진입, 외부 Post, Study 단독, GUI↔CLI/Python/MCP 동일 owner, 이동 사본, Windows 비WSL | Workbench/AI/WSL을 모든 진입의 필수로 강제, 다른 store/사용자 창 제어, 원 store 없으면 결과 열기 실패 |

원 PRODUCT_PLAN의 세 사례도 삭제하지 않는다. A는 J2와 명시 DP의 실제 재료점·FE/holdout 비교, B는 지그 강성·마찰·체결·편심과 동일 gauge 비교, C는 열 곡률·계면 손상·재닫힘·점탄성 회복과 관측시점 비교다. 이들은 전체 17개 UC의 대표 통합 장면이며 전체 명세를 대신하지 않는다. 공차·장비 한계·물성 미제공이면 제작/불량 판단은 UNKNOWN으로 남기되 기술 workflow는 구현한다.

### 13.4 계획의 최종 종료 조건

B1–B8의 작업과 부록의 74개 원행을 한 번씩 대조해, 실제 남은 코드가 없고 인도 조건이 충족된 행만 닫는다. 처음 ‘완료 대조’였던 행도 실제 누락이 발견되면 그 누락을 고친 후 닫는다. MoAI task·SPEC status·README·CURRENT_STATE의 표현도 같은 결과와 일치시킨다.

필수 지원 기능에 실제 adapter/계산/재열기가 없으면 전체 제품 완료가 아니다. 장비·원격 호스트의 실제 입력이 없는 조건부 행은 별도 미확인으로 남기고 ‘사용 가능한 소프트웨어 인도 범위 완료, 외부 연결 인수 미완료’라고 정확히 보고한다. 기존 미확인을 삭제하거나 수치를 바꿔 ‘74행 완료’를 만드는 종료 방법은 허용하지 않는다.

## 14. Codex 가정에 대한 수정안

현재 제안/코드의 실제 불일치와, 옛 계획을 새 배정에 적용할 때의 위험을 구별한다. 현재 기록은 셸·빔·M3·NS1 부모 행을 이미 부분 상태로 유지하고 있다. 이를 Codex가 전체 완료를 주장했다는 비판으로 바꾸지 않는다.

| 현재 자료의 가정/위험 | 판단 | 적용할 수정 |
|---|---|---|
| `remaining_work.md`: NS2 산출물 미회수 | 최신 request와 모순. 실제 없는 ZIP을 기다릴 이유 없음 | 기존 dynamic 기반과 충분한 소스/요구를 새 Pro NS2/N3 요청으로 전달. 회수/적용 상태로 기록하지 않음 |
| 같은 메모: Post/충격에 B1 실제 결과 ID를 선행 요구 | 독립 Post와 충격 입력 개발을 불필요하게 직렬화 | 외부/보존 결과로 B3 즉시 진행. B2 충격은 기존 FE adapter 기반 병행. 해당 왕복 검사 때만 B1 결과 사용 |
| M4 outer Placement/BREP 직접 동일 비교 | 표현 동일성과 실제 형상/선택 자세 동일성을 혼동 | 세계 형상과 native 대응을 비교하되 source identity/참조/pose를 별도 보호. bbox/중심만으로 완화하지 않음 |
| 제한된 성공을 부모 기능 완료로 확대할 위험 | 아직 있는 복합재·체결·접촉·동역학·결과 잔여를 숨김 | 첫 사용 인도와 원행 완료를 별도 기록. 동일 FN 아래 후속 작업 유지 |
| D5 전체를 `SPEC-RESEARCH-003`으로 대표 | 실제 SPEC 범위가 주로 FN-08/18/19 | D5 원행과 FUNCTION_SPEC를 유지하며 기존 Desktop/Numerical/law SPEC에 실제 연결 추가 |
| 옛 D7 plan의 D6 인도 기준·WSL 우선 서술을 새 배정에 그대로 적용 | 이미 있는 D7 구현을 다시 기다리게 하거나 Windows 비WSL 조건을 잃을 위험 | 필요한 평가기/field 계약만 선행. 기존 D7는 계속 통합하고 native 지원 계산과 Linux 선택 capability 분리 |
| 기존 local RBF를 전역 numeric archive로 그대로 재열기 | 현재 archive는 neighbors를 의도적으로 제외 | 별도 local-model 저장/명시 예측 계약 작성. 재열기에 fit/predict 호출 금지 |
| `agent/workflow`, SPEC audit PASS를 실제 실행/완성으로 오해할 위험 | 도구 능력과 산출물을 과장 | 실제 Codex 협업과 Pro UI를 사용. MoAI는 조회/관리/분석/동기화 역할로만 기록 |
| 배포·복구·동등 명령을 모든 개발 뒤에 처리 | 마지막에 서로 다른 owner/저장 의미가 충돌 | B8 필수 연결과 I0 계약부터 병행. 각 인도에 저장/실패/재열기 포함 |
| 장비/host 없음 또는 사용자 공학 기준 없음이 전체 중단 사유 | 의존하는 실제 실행에만 해당 | 해당 행의 외부 입력만 명시. 나머지 독립 구현·공개 기술 검증 계속 |

## 15. 노력·위험과 실제 착수 지시

정확한 출시일은 산정하지 않는다. 아래는 일정 약속이 아닌 상대적 작업량과 분할 기준이다.

| 범위 | 상대 노력 | 가장 큰 위험 / 통제 |
|---|---|---|
| B1 첫 왕복·M4 교정 | 중 | native 표현/참조·현재 미커밋 충돌. 기존 실패 입력과 의미 있는 변조 반례로 한정 교정 |
| B1 고급 요소·접촉·체결 | 매우 큼 | backend capability·요소/law 조합. E/C/R별로 작동하는 업무를 인도하고 조합 검증을 별도 유지 |
| B2 NS2/N3·restart | 큼 | 상태/시간·solver checkpoint 호환. 초기조건→연속 단계→restart의 명확한 세 하위 인도 |
| B2 일반 충격·손상·피로 | 매우 큼 | card 변환·에너지·법칙 교정. 입력, 응답, 법칙별 인도로 분리하고 누락 card/자료 차단 |
| B3/B4 | 중~큼 | 물리 측도·mask/후보 보존·multi-owner 의미. 기존 reader/owner와 작은 기준 재사용 |
| B5/B6 | 큼~매우 큼 | typed 변수·local model·gradient·mapping·runtime. 독립 분석과 계산 capability를 병행 분리 |
| B7 | 중, 실장비 별도 | 실제 provider/문헌/교정·장비 권한. 기존 구독 경로 유지, 없는 외부 자료 합성 금지 |
| B8 | 큼, 원격 환경 별도 | copy/ref·부분 저장·프로세스 소유. 첫 인도부터 통합하고 마지막에만 검증하지 않음 |

**다음 실제 작업:** Codex는 현재 M4/Sol 변경을 보존한 채 I0의 네 계약과 파일 소유를 현재 작업표에 붙인다. Pro에는 NS2/N3 새 요청과 B4 핵심 요청을 각각 실제 코드·원행·입출력·실패/인수 조건과 함께 전달한다. Sol Post는 B3.1을 계속하고 Research Sol은 계약이 고정된 B4/B5 패널을 작성한다. Luna는 장비 없는 추상 조사 대신 해당 backend/파일과 MoAI 실제 호출 가능성을 확인한다. Astra는 M4 동일성·동적 상태/restart·mixed-control의 반례부터 검토한다. 이후 완료된 기능을 I1/I2부터 즉시 통합·게시한다. 새 기획 회차나 재승인을 기다리지 않는다.


## 부록 A. 원 74행과 실행 작업의 일대일 주 배정

각 행의 원 요구 번호와 `moai_acceptance`, `acceptance` 문구를 보존했다. 현재 분류는 기획 CSV의 상태가 아니라 `current/CURRENT_STATE.md`의 24행/50행 표다. “완료”는 기존 지원 범위의 완료를 유지한다. “완료 대조”는 새 기능 구현으로 세지 않는다. 교차 기여는 실행 칸에만 표시하므로 행 수는 늘어나지 않는다.

기존 AC-Dxx는 `SPEC-DESKTOP-001`이다. 추가 연결 약칭은 PREFE=`SPEC-PREFE-001`, IMPACT=`SPEC-IMPACT-001`, RESEARCH=`SPEC-RESEARCH-003`, NUMERICAL-002=`SPEC-NUMERICAL-002`, POST-COMPARE=`SPEC-POST-COMPARE-001`, EXPERIMENT=`SPEC-EXPERIMENT-001`, EXPERT=`SPEC-EXPERT-001/002`, DESKTOP=`SPEC-DESKTOP-001/002`다. 번호 체계가 다른 SPEC에 새 AC 번호를 만들어 맞추지 않는다.

### B1 설계·조립·구조해석 — 15행

| 원행 / 현재 | 실행 작업·추가 SPEC | 원 요구·기존 MoAI AC | 원행 완료 조건 — 원문 |
|---|---|---|---|
| FN-10-01 / 완료 | §3 보존·I1; PREFE AC-01 | R04;R06;R07;R08;R25;R26 / AC-D03;AC-D11 | constraint 재정렬 뒤 같은 semantic target 또는 명시 수리; 원 CAD 보존 |
| FN-10-02 / 완료 | §3 보존·I1; PREFE AC-02 | R04;R06;R07;R08;R25;R26 / AC-D03;AC-D11 | 무반응 관측이 전역 free 변수 금지로 확대되지 않음 |
| FN-11-01 / 부분 구현 | B1.1–2; PREFE AC-03 | R01;R07;R11;R12;R26;U§6 / AC-D03;AC-D11 | old restore가 새로운 P1 adoption을 되돌리지 못함 |
| FN-11-02 / 완료 | B1.1–2 관련 회귀; PREFE AC-04 | R01;R07;R11;R12;R26;U§6 / AC-D03;AC-D11 | cancel request/unsupported/terminal/restore를 실제 native 상태로 표시 |
| FN-12-01 / 완료 | B1.3–4 관련 회귀; PREFE AC-05 | R01;R08;R19;R26;R29;R30 / AC-D03;AC-D11 | 잘못된 body/face·중복/누락을 3D와 table에서 함께 수정 |
| FN-12-02 / 부분 구현 | B1.3–4·B2.1; PREFE AC-06 | R01;R08;R19;R26;R29;R30 / AC-D03;AC-D11 | 지원되지 않는 card는 draft 저장·실행 차단; raw include 보존 |
| FN-13-01 / 완료 | §3 보존·I1; PREFE AC-07 | R08;R09;R26;R29;R34 / AC-D03;AC-D11 | 불량 element를 선택·격리·수정·재생성·비교 |
| FN-13-02 / 완료 | §3 보존·I1; PREFE AC-08 | R08;R09;R26;R29;R34 / AC-D03;AC-D11 | stale mesh는 보존되고 적용하지 않음; 취소와 종료 구분 |
| FN-14-01 / 부분 구현 | B1.5; PREFE AC-09 | R01;R08;R19;R26;R29;R30 / AC-D03;AC-D11;AC-D04 | 두 set/normal arrows/실제 gap과 입력 policy 확인; 미지원 저장 가능·run block |
| FN-14-02 / 부분 구현 | B1.6·B3.3; PREFE AC-10 | R01;R08;R19;R26;R29;R30 / AC-D03;AC-D11;AC-D04 | 실제 pressure/force/gap/slip의 단위·위치·부호·time를 독립 검증 |
| FN-14-03 / 완료 | B1.5 관련 회귀; PREFE AC-11 | R01;R08;R19;R26;R29;R30 / AC-D03;AC-D11;AC-D04 | Cancel은 old refs unresolved 유지; Apply는 새 geometry/contact rev와 재preflight |
| FN-15-01 / 부분 구현 | B1.6·B2.1–4; PREFE AC-12 | R01;R14;R26;R29 / AC-D03;AC-D11;AC-D04 | 물리 time/iteration/walltime 분리; 실패 increment→원설정 수정 |
| FN-15-02 / 부분 구현 | B1.6·B2.1–4; PREFE AC-13 | R01;R14;R26;R29 / AC-D03;AC-D11;AC-D04 | 각 physics 기준을 충족한 조합만 run enabled; 다른 도구의 선행 gate 없음 |
| FN-25-01 / 완료 | §3 보존·B2.3; PREFE AC-14 | R08;R12;R20;R21;R34 / AC-D03;AC-D11;AC-D06 | 같은 job/result/input을 열고 status 관측만으로 submit 없음 |
| FN-25-02 / 완료 | §3 보존·B2.4; PREFE AC-15 | R08;R12;R20;R21;R34 / AC-D03;AC-D11;AC-D06 | 늦은 결과 보존; 종료 미확인 자동 retry/kill 금지 |

### B2 동역학·충격·손상 — 4행

| 원행 / 현재 | 실행 작업·추가 SPEC | 원 요구·기존 MoAI AC | 원행 완료 조건 — 원문 |
|---|---|---|---|
| FN-16-01 / 부분 구현 | B2.5; IMPACT FN-16-01 | R01;R15;R30 / AC-D03;AC-D11 | 미지원 card 누락 없이 차단; 측정 v/ω와 height-derived mode 분리 |
| FN-16-02 / 부분 구현 | B2.6·B3; IMPACT FN-16-02 | R01;R15;R30 / AC-D03;AC-D11 | 정확 physical time·added mass·energy balance·failure 및 원값을 남김 |
| FN-17-01 / 부분 구현 | B2.6·B1.5; IMPACT FN-17-01 | R01;R17;R29;R30;R31 / AC-D03;AC-D11 | bulk와 interface damage·reclosure 결과를 따로 추적 |
| FN-17-02 / 부분 구현 | B2.6; IMPACT FN-17-02 | R01;R17;R29;R30;R31 / AC-D03;AC-D11 | 단일 cycle을 수명으로 표시하지 않고 요구/미확인 보존 |

### B3 독립 Post — 5행

| 원행 / 현재 | 실행 작업·추가 SPEC | 원 요구·기존 MoAI AC | 원행 완료 조건 — 원문 |
|---|---|---|---|
| FN-27-01 / 확인 보류 | B3.1·3; POST-COMPARE; §5 | R10;R12;R13;R20 / AC-D03;AC-D11 | 정확 source/time/association↔3D/표/곡선 선택 일치 |
| FN-27-02 / 부분 구현 | B3.1; POST-COMPARE; §5 | R10;R12;R13;R20 / AC-D03;AC-D11 | 관리 Ctrl+S/close save가 동일 관문; native stock 설정은 별도 |
| FN-28-01 / 완료 | B3.2 관련 회귀; POST-COMPARE; §5 | R10;R11;R19;R20;R34 / AC-D03;AC-D11 | 동일 tet 또는 B→A scalar만 지원; percent mask와 delta mask 구분 |
| FN-28-02 / 부분 구현 | B3.2; POST-COMPARE; §5 | R10;R11;R19;R20;R34 / AC-D03;AC-D11 | 필수 F/J·coordinate/time mapping 없으면 해당 field diff 차단 |
| FN-28-03 / 완료 | B3.4; POST-COMPARE; §5 | R10;R11;R19;R20;R34 / AC-D03;AC-D11 | 원 A 정상 유지·새 B branch로만 변경; retained old result 보존 |

### B4 Data·Material — 12행

| 원행 / 현재 | 실행 작업·추가 SPEC | 원 요구·기존 MoAI AC | 원행 완료 조건 — 원문 |
|---|---|---|---|
| FN-03-01 / 완료 대조 | B4.6; §6 SPEC 연결 | R10;R12;R19;R20;R32;U§5;U§6 / AC-D03;AC-D11 | B 1250 µm→1.25 mm, 0.01 kN→10 N, 1000 ms→1 s를 원행과 대조 |
| FN-03-02 / 추가 개발 | B4.2; §6 SPEC 연결 | R10;R12;R19;R20;R32;U§5;U§6 / AC-D03;AC-D11 | 현재면적/J 없이 true stress 요청은 차단; invalid draft 저장 |
| FN-04-01 / 완료 대조 | B4.6; §6 SPEC 연결 | R10;R12;R20;R32;U§6 / AC-D03;AC-D11 | hide가 통계 제외를 바꾸지 않고 mask Undo는 원 row를 보존 |
| FN-04-02 / 추가 개발 | B4.1; §6 SPEC 연결 | R10;R12;R20;R32;U§6 / AC-D03;AC-D11 | 비단조·gap·NaN 원자료 보존; 허용된 연산만 실행; 큰 파일 전체 UI reload 방지 |
| FN-04-03 / 완료 대조 | B4.6; §6 SPEC 연결 | R10;R12;R20;R32;U§6 / AC-D03;AC-D11 | 품질 제외 finite sample·Plan 제외 sample은 raw/화면에 남되 objective에 포함되지 않음; hide와 holdout 독립 |
| FN-06-01 / 추가 개발 | B4.2–3; §6 SPEC 연결 | R01;R17;R20;R29 / AC-D03;AC-D11 | 현재 실제 F·time·stress measure를 저장 결과에서 확인 |
| FN-06-02 / 추가 개발 | B4.3; §6 SPEC 연결 | R01;R17;R20;R29 / AC-D03;AC-D11 | 동일 axial stretch에서 자유 횡응력≈0; 고정 F22/33와 구별; 실패 state 보존 |
| FN-07-01 / 완료 대조 | B4.6·B8.2; §6 SPEC 연결 | R01;R17;R18;R20;R27;R32 / AC-D03;AC-D11 | Material+Plan 동시 dirty·trial roles·정확 source ref를 한 화면에서 편집 |
| FN-07-02 / 추가 개발 | B4.4; §6 SPEC 연결 | R01;R17;R18;R20;R27;R32 / AC-D03;AC-D11 | 없는 곡선/holdout은 없음 표시; 행 선택 무계산; 명시 평가만 새 ref, source masks 실제 objective 적용 |
| FN-07-03 / 완료 대조 | B4.6; §6 SPEC 연결 | R01;R17;R18;R20;R27;R32 / AC-D03;AC-D11 | r17 fit 결과를 r18에 silent overwrite하지 않고 새 revision과 provenance를 보존 |
| FN-09-01 / 추가 개발 | B4.5·B6.1; §6 SPEC 연결 | R17;R19;R26;R29;R30 / AC-D03;AC-D11 | 미지원 조합·누락 failure 계수를 숨기지 않고 export 차단 |
| FN-09-02 / 완료 대조 | B4.6; §6 SPEC 연결 | R17;R19;R26;R29;R30 / AC-D03;AC-D11 | 성공 exit와 stress/strain/energy 동등성 구분 |

### B5 Numerical — 11행

| 원행 / 현재 | 실행 작업·추가 SPEC | 원 요구·기존 MoAI AC | 원행 완료 조건 — 원문 |
|---|---|---|---|
| FN-20-01 / 추가 개발 | B5.1; NUMERICAL-002; §7 | R18;R27;R31;R40 / AC-D03;AC-D11;AC-D04 | 행 선택→원입력/응답, rank deficient 표시와 failed 후보 보존 |
| FN-20-02 / 추가 개발 | B5.2; NUMERICAL-002; §7 | R18;R27;R31;R40 / AC-D03;AC-D11;AC-D04 | ordinary LHS/누락 결과/순서 변경은 Sobol 차단 |
| FN-20-03 / 추가 개발 | B5.1; NUMERICAL-002; §7 | R18;R27;R31;R40 / AC-D03;AC-D11;AC-D04 | 종속/비연속 변수를 continuous rounding으로 속이지 않음 |
| FN-21-01 / 추가 개발 | B5.3; NUMERICAL-002; §7 | R18;R27;R31;R32 / AC-D03;AC-D11;AC-D04 | 가짜 응답·penalty 혼입 없이 best feasible/failed/infeasible 구분 |
| FN-21-02 / 추가 개발 | B5.4; NUMERICAL-002; §7 | R18;R27;R31;R32 / AC-D03;AC-D11;AC-D04 | gradient 지원이 없으면 해당 method만 unavailable; 일반 search 유지 |
| FN-22-01 / 추가 개발 | B5.2; NUMERICAL-002; §7 | R18;R31;R32 / AC-D03;AC-D11 | 실패 표본 포함 전체 수·조건부 통계·tail bounds를 표시 |
| FN-22-02 / 추가 개발 | B5.2; NUMERICAL-002; §7 | R18;R31;R32 / AC-D03;AC-D11 | PSD/unit/순서 검사; correlation 미지원이면 explicit block |
| FN-23-01 / 추가 개발 | B5.5; NUMERICAL-002; §7 | R18;R31 / AC-D03;AC-D11 | 학습점 중복 거절·out_of_range와 PREDICTED 명시 |
| FN-23-02 / 추가 개발 | B5.6; NUMERICAL-002; §7 | R18;R31 / AC-D03;AC-D11 | 재열기 숨은 학습/solve 없음; 확인 결과는 새 evaluation |
| FN-24-01 / 추가 개발 | B5.6; NUMERICAL-002; §7 | R18;R31;R40 / AC-D03;AC-D11;AC-D05;AC-D07 | total budget·directions·infeasible 보존과 정확한 점/결과 |
| FN-24-02 / 추가 개발 | B5.6·B6.4; NUMERICAL-002; §7 | R18;R31;R40 / AC-D03;AC-D11;AC-D05;AC-D07 | 새 scheduler 없이 domain/Plan 경계 유지·설계 동기화 검증 |

### B6 구성식·PDE·연성 — 7행

| 원행 / 현재 | 실행 작업·추가 SPEC | 원 요구·기존 MoAI AC | 원행 완료 조건 — 원문 |
|---|---|---|---|
| FN-08-01 / 완료 대조 | B6.1; RESEARCH FN-08-01 | R01;R17;R29;R31;R39 / AC-D03;AC-D11;AC-D05;AC-D07 | 선택 증분→state/residual/tangent 원값·입력 ref를 조회 |
| FN-08-02 / 추가 개발 | B6.1·B4.5; RESEARCH FN-08-02 | R01;R17;R29;R31;R39 / AC-D03;AC-D11;AC-D05;AC-D07 | 지원 pair/finite strain/interface별 증거가 없으면 해당 실행·export 차단 |
| FN-18-01 / 완료 대조 | B6.2; RESEARCH FN-18-01 | R01;R16;R28;R31 / AC-D03;AC-D11;AC-D04 | 현재 bounded AST/unit1를 정확히 보여주고 declared input을 바꿈 |
| FN-18-02 / 완료 대조 | B6.2; RESEARCH FN-18-02 | R01;R16;R28;R31 / AC-D03;AC-D11;AC-D04 | 미지원 방정식 draft 저장·실행 차단; 지원 equation 독립 기준 충족 |
| FN-19-01 / 완료 대조 | B6.4; RESEARCH FN-19-01 | R01;R16;R19;R20;R31 / AC-D03;AC-D11 | Plan 없이 같은 kind=evaluation 문서를 저장/평가·Plan은 exact ref |
| FN-19-02 / 추가 개발 | B6.3; RESEARCH FN-19-02 | R01;R16;R19;R20;R31 / AC-D03;AC-D11 | 실제 공급/수신 field와 ΔL=α(T−Tref)L 기준; ΔT offset 중복 금지 |
| FN-19-03 / 완료 대조 | B6.4; RESEARCH FN-19-03 | R01;R16;R19;R20;R31 / AC-D03;AC-D11 | NOT_CONVERGED는 유효 목적값 아님; 반복 partial checkpoint 미지원 유지 |

### B7 Study·Expert·실험·보고 — 9행

| 원행 / 현재 | 실행 작업·추가 SPEC | 원 요구·기존 MoAI AC | 원행 완료 조건 — 원문 |
|---|---|---|---|
| FN-05-01 / 추가 개발 | B7.3; EXPERIMENT; §9 | R10;R11;R20;R32 / AC-D03;AC-D11 | raw→보정값→동일 관측량→판단의 정확 refs를 재열기 |
| FN-05-02 / 추가 개발 | B7.4·B5.3; EXPERIMENT; §9 | R10;R11;R20;R32 / AC-D03;AC-D11 | 미식별 계수는 fixed/unidentified로 보이고 다른 시험을 기록 |
| FN-29-01 / 완료 대조 | B7.1; EXPERT; §9 | R02;R03;R10;R11;R13;R32 / AC-D03;AC-D11 | Study 단독 생성/저장; Expert 없이 판단·후속 문서 열기 |
| FN-29-02 / 완료 대조 | B7.1; EXPERT; §9 | R02;R03;R10;R11;R13;R32 / AC-D03;AC-D11 | 새 evidence 자동 decision 변경 금지; invalid ref는 repair 가능 |
| FN-29-03 / 추가 개발 | B7.1; EXPERT; §9 | R02;R03;R10;R11;R13;R32 / AC-D03;AC-D11 | URL만 붙여도 근거 확인됨으로 표시하지 않고 원문 위치가 열리며 누락/변경 branch를 식별 |
| FN-30-01 / 완료 대조 | B7.2; EXPERT; §9 | R02;R03;R13;R20;R32 / AC-D03;AC-D11 | reply 대상/실제 source·provider author·Plan draft가 보존 |
| FN-30-02 / 완료 대조 | B7.2; EXPERT; §9 | R02;R03;R13;R20;R32 / AC-D03;AC-D11 | no-provider/limit은 drafts 유지; 유료 fallback·자동 provider 전환 금지 |
| FN-32-01 / 추가 개발 | B7.5; EXPERIMENT; §9 | R09;R10;R11;R12;R20;R32;R34;R52 / AC-D03;AC-D11 | 수치/plot/판단 source를 재열고 실패/UNKNOWN/NOT_RELEASED 유지 |
| FN-35-01 / 추가 개발 | B7.6; EXPERIMENT; §9 | R01;R31;R32;R35 / AC-D03;AC-D11 | 실측 data/장비 종료 acknowledgment·실험 input과 보정 lineage 확인 |

### B8 일상 사용·배포·공통 연결 — 11행

| 원행 / 현재 | 실행 작업·추가 SPEC | 원 요구·기존 MoAI AC | 원행 완료 조건 — 원문 |
|---|---|---|---|
| FN-01-01 / 완료 대조 | B8.1; DESKTOP; §10 | R12;R13;R21;R33;U§1;U§5 / AC-D03;AC-D11 | 동일 store/doc는 기존 owner 활성화; 다른 store는 구별; 결과 열기 무실행 |
| FN-01-02 / 추가 개발 | B8.3; DESKTOP; §10 | R12;R13;R21;R33;U§1;U§5 / AC-D03;AC-D11 | 이동용 사본이 원 store 없이 열리고 원본·이전 결과가 불변 |
| FN-02-01 / 추가 개발 | B8.2; DESKTOP; §10 | R08;R11;R12;R13;R19;R20;U§6 / AC-D03;AC-D11;AC-D05;AC-D07 | Enter/Esc/Undo/멀티owner paste가 대상 owner만 변경 |
| FN-02-02 / 추가 개발 | B8.2; DESKTOP; §10 | R08;R11;R12;R13;R19;R20;U§6 / AC-D03;AC-D11;AC-D05;AC-D07 | Material만 성공해도 Plan 실패와 old reference 보존; 재열기 무계산 |
| FN-02-03 / 완료 대조 | B8.2·I0; DESKTOP; §10 | R08;R11;R12;R13;R19;R20;U§6 / AC-D03;AC-D11;AC-D05;AC-D07 | 동일 필드 stale 덮어쓰기 금지; 재승인 없는 새 ID 자동 재시도 금지 |
| FN-26-01 / 완료 대조 | B8.4; DESKTOP; §10 | R18;R31;R35 / AC-D03;AC-D11;AC-D06 | stale exchange/duplicate/값변경 거절; missing은 NOT_EVALUATED |
| FN-26-02 / 추가 개발 | B8.4; DESKTOP; §10 | R18;R31;R35 / AC-D03;AC-D11;AC-D06 | reconnect에 중복 submit 없음; 실제 job termination과 file checksum 확인 |
| FN-31-01 / 추가 개발 | B8.5; DESKTOP; §10 | R11;R13;R19;R33 / AC-D03;AC-D11 | drag/menu 동등; broken과 new revision 별도; 원본 편집 없음 |
| FN-33-01 / 완료 대조 | B8.6; DESKTOP; §10 | R13;R14;R15;R16;R35;R39;U§1;U§2 / AC-D03;AC-D11 | 도구 선택 없이 파일로 바로 맞는 owner; browser 주화면 없음 |
| FN-33-02 / 완료 대조 | B8.6; DESKTOP; §10 | R13;R14;R15;R16;R35;R39;U§1;U§2 / AC-D03;AC-D11 | version probe만으로 solver benchmark/GUI 수용 PASS 표시 금지 |
| FN-34-01 / 완료 대조 | B8.6·I1–4; DESKTOP; §10 | R02;R13;R19;R20;R21;R43 / AC-D03;AC-D11 | 같은 결과 refs·actual values/selection; fake success나 active doc 추정 없음 |

## 부록 B. 원 52절의 비기능 요구와 읽을 위치

R 번호의 기능 연결은 부록 A의 원 요구 열을 따른다. 그 표에 직접 나타나지 않는 개발·운영·역사 요구도 삭제한 것이 아니다. `current/PROJECT_SCOPE.md`의 Original section ledger와 Preserved detailed acceptance inventory, `current/docs/REQUIREMENTS_VALIDITY_REVIEW.md` 부록 A의 현재 효력을 그대로 적용한다.

| 원요구 유형 | 이 계획의 적용 위치 |
|---|---|
| R02/03/05/06/19/20/21 공통 책임·모델·명령 | §2의 owner/field/Plan 계약, B4/B6/B7/B8. OpenScience는 선택 진입이며 Core를 우회하지 않음 |
| R04/22/41 기존 자산 재사용·실제 소스 감사 | 각 B의 기존 코드와 수정 지점. 새 프레임워크·고정 예제 복제 금지 |
| R08/09/10/11/12/34 정확성·자료·검사 | §2·13. invalid draft와 원결과 보존, 부분 실패·UNKNOWN을 별도 유지 |
| R14/15/16/17/18/35/39/40 backend·환경·법칙 조사 | B1/B2/B4/B5/B6/B8의 실제 누락 capability만 조사. 모든 후보 설치를 인도 조건으로 만들지 않음 |
| R23/24/36/49/50/51 초기 순서·이력·중요 결정 | §1·11·12. 기존 상태와 중요한 계약만 갱신하고 초기 시범·승인 절차를 반복하지 않음 |
| R37/38/42/43/44/45/46/47 병렬·검토·통합 | §11의 파일 소유·실제 대화·독립 검토·루트 순차 통합 |
| R25–32/48/52 실제 전체 연구 연결과 진척 | B1–B8·§13 종합 왕복. 기능 수나 문서 수 대신 사용자가 끝낸 업무로 인도 |

### 자료와 코드의 기준 위치

첨부의 `request.md`는 최신 지시, `current/`는 현재 운영 기록과 M4 변경, `baseline/`은 기준 코드다. 아래 경로는 ZIP 내부 경로이며 다른 대화나 현재 원격 저장소를 읽었다는 뜻이 아니다. 이 문서는 제품 소스·CURRENT_STATE를 변경하지 않는다.

| 용도 | 실제 읽은 기준 위치 |
|---|---|
| 최신 사실·분류 | `current/CURRENT_STATE.md` 상단; “전처리·FE 솔버·후처리 세부 진도”, “독립 연구 도구와 전체 연결의 남은 작업” |
| 전체 사용자 요구·현재 효력 | `current/PROJECT_SCOPE.md`; `current/docs/REQUIREMENTS_VALIDITY_REVIEW.md`; `current/docs/PRODUCT_PLAN.md`와 A/B/C 사례; `current/docs/CODEX_WORKFLOW.md` |
| 기능 원문과 74행 | `baseline/docs/design/20261012-desktop-planning/pro-authored/FUNCTION_SPEC.md` FN-01–35·C01–C05; 같은 설계 폴더의 `pro-ux/implementation_map.csv` |
| 비교 대상으로만 사용한 제안 | `current/remaining_work.md`. 최신 지시와 어긋난 선행/NS2 서술은 §14에서 수정 |
| 기존 SPEC | `baseline/.moai/specs/` 아래 각 B에 명시한 SPEC의 spec/plan/acceptance. 오래된 draft/status 및 과거 “승인 뒤 시작”은 현재 구현 판정으로 사용하지 않음 |
| M4 실제 변경 | `current/apps/desktop_pre/assembly_pose_geometry.py`; `assembly_pose_candidate.py`. 기존 geometry/occurrence 비교는 baseline의 `apps/desktop_pre/occurrence_fem.py`, `projects.py` 등과 대조 |
| native 편집·Post | `baseline/apps/desktop_pre/`, `baseline/apps/desktop_post/`. 각 B1/B2/B3 표의 해당 파일·함수만 수정 대상으로 지정 |
| domain·adapter·수치 엔진 | `baseline/caelab/`, `baseline/caelab/adapters/`, `baseline/caelab/optimizers/`, `baseline/caelab/assist/`의 각 B4–B8 지정 파일 |
| Qt·공통 명령 | `baseline/apps/research/`, `baseline/openscience/workbench_mcp.py`; 공통 경계는 Codex 단독 통합 |

ZIP에는 루트 Windows 시작 scripts와 일반 tests 폴더가 포함되지 않았다. 해당 동작은 현재 기록/명세에서 확인했으며 스크립트 원문과 기존 test 파일은 실제 Codex checkout에서 확인한 뒤 수정한다. 따라서 이 문서는 존재하지 않는 test 경로나 Windows 실행 결과를 제출물로 표시하지 않는다. 신규 제안 파일은 해당 작업의 파일명이며 현재 존재하는 구현이 아니다.


**인계의 적용:** 이 문서를 기존 작업표/SPEC에 연결한 뒤 곧바로 해당 코드와 사용자 인도를 진행한다. 새 병렬 작업이 바꾸지 않는 기존 완료 기능과 진행 중 작업은 계속 유지한다.
