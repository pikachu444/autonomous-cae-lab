# 기능별 검증 매뉴얼

사용은 [설치 안내](INSTALL_KO.md), [처음 시작하기](USER_GUIDE_KO.md),
[화면별 사용법](SCREEN_GUIDE_KO.md)에서 시작한다. 이 문서는 개발·검증 담당자의 현행
절차·기준·명령·결과 입구다. 현재 배정은 [CURRENT_STATE](../CURRENT_STATE.md) 한 곳에서 관리한다.

교정 회차마다 acceptance 문서나 일회성 시작 스크립트를 만들지 않는다. 검사는 기존
기능별 `tests/`와 `scripts/native_check.py`에 통합한다. 날짜별 입력·실패·출력·로그는
원 기록으로 보존하고 이 문서에서 연결한다. 파일 수를 제품 완성도로 세지 않는다.

## 검증의 구분

**10월19일 Workbench 연결 표시:** 선택 항목과 직접 연결된 카드/관계표를 기본으로 하고
전체 배치·수동 좌표·정확한 owner/ref 열기를 유지한다. 관련 Qt 13PASS, 같은 저장 묶음의
실제 Windows 동선 1PASS와 최종 전체 배치 1PASS, 이동·새 창 복원 1PASS. 51항목/59연결의
일반·1100 창에서 카드·관계·한국어를 읽었고, 실제 원본 선택 목록 Esc 취소와 원 파일/Jobs
불변을 확인했다. 원점 좌표 누락으로 임시 좌표가 전체 배치에 남던 시각 P2를 초기 좌표의
명시 보관으로 고쳤다. 같은 Astra의 한정 통합 검토에 미해결 P1/P2는 없다. 앱 열기는
정확 ref를 받은 callback 범위이며 자식 앱 실제 실행은 이번에 확인하지 않았다. 복원은
새 창 범위다. 물리 계산/새 solver/provider0. 이전 49연결 그림과는 데이터 시점이 다르다.
근거는 `_workspace/connection-ux-20261019/{actual-02,actual-final,process-overview-04,process-resume-final-08}`의
실제 캡처·원 실행 기록과 [연결 화면](SCREEN_GUIDE_KO.md#문서-연결에서-관계와-이동-사본-확인하기)이다.

The established solvers' published verification cases and documented limits
are upstream evidence. Reuse that evidence for the applicable solver version,
formulation and feature; the Lab is not a replacement certification programme
for every solver algorithm. Code_Aster provides a dedicated validation manual;
CalculiX distributes solver test examples and theory/user documentation:
[Code_Aster validation](https://code-aster.org/doc/v16/index.html),
[CalculiX official solver documentation and test examples](https://www.dhondt.de/).

Keep these scopes distinct in work plans and acceptance records:

| Scope | What is established | Required local evidence |
| --- | --- | --- |
| Upstream numerical verification | Published cases exercise specified algorithms/formulations under their stated conditions. | Exact reference, version/conditions and documented limits; do not infer all-feature approval. |
| Installed adapter/integration verification | The Lab's actual version, input conversion, execution and result reader reproduce the intended problem. | Representative applicable reference case, actual inputs/units/materials/loads/boundaries, native outputs, independent response comparison and complete provenance. |
| Research model assessment | The chosen geometry, mesh, contact/joints, material and idealisations are adequate for the stated research question. | Problem-specific assumptions, meaningful mesh/time-step sensitivity, equilibrium/convergence and analytical/reference/cross-solver comparison where available. |
| Physical/engineering qualification | The prediction is adequate for the intended real specimen, machine, strength/durability and deployment. | Required measured data, physical comparison and approval; missing evidence remains UNKNOWN/NOT_RELEASED. |

A solver's normal exit does not prove correct input mapping, correct parsing,
an adequate engineering model or release. Conversely, a reference mismatch is
not automatically an upstream solver defect: retain the native data and
separate modelling, discretisation, adapter, environment and algorithm causes
until evidence identifies them.

Use established representative benchmarks to qualify the connection, then
reuse the passing source/run evidence. Recheck the affected integration or
model when its source, runtime, formulation, mesh/conditions or admitted
feature changes. Do not rerun the complete upstream suite or unchanged native
experiments solely to create another checkpoint. Artifact-integrity checking
when consuming a retained result is a separate operation from a solver rerun.

The original-fixture assembly work in ADR0032 is CAD-parent integration:
captured parametric input/source, native component/face/interface identity,
pre-export rejection, same-revision artifacts and human inspection. Initial
geometric contact distance is not a solved pressure/gap or preload result.
Its nonlinear fixture mechanics and whole OpenScience campaign remain later
gates. Numerical engines retain search ownership; OpenScience asks questions,
selects campaigns and interprets qualified evidence through the common Core.

## 실행 전 준비

1. Git 커밋·runtime·선택 문서와 저장 결과를 고정하고 변경된 기능과 의존 경로를 검사한다.
   변하지 않은 전체 솔버 캠페인은 다시 실행하지 않는다.
2. 아래 `python`은 설치 안내의 전용 실행 환경이다. pytest의 통과·실패·건너뜀을 구분한다.
   의존성이나 원자료가 없어 건너뛴 검사는 실제 성공이 아니다. 대역의 경계도 명시한다.
3. 실제 GUI 검사는 한 담당씩 수행한다. 일반/좁은 창, 한국어, 초점/선택, 취소와 복구를
   확인하며 Qt event 검사와 전체 OS 조작을 구분한다.
4. 실제 앱/솔버는 기존 공통 실행기와 새 출력 폴더를 사용한다. 자신의 root/자식만 정리하고
   `native-check.json`의 exit code·timeout·cleanup 및 stdout/stderr를 확인한다.

```powershell
python scripts/native_check.py --timeout 180 --output-dir runs/새검사/process -- 실행파일 인수
```

전용 검사가 특정 보존 fixture를 요구하면 정확한 입력을 확인한다. 없는 자료를 임의로
바꿔 이전 인수의 재현이라고 하지 않는다. 읽기·복구 검사에서 새 solver/provider 호출을
금지했다면 호출 시 실패다. 수치 허용값을 완화하거나 실패값을 보정해 통과시키지 않는다.

## 설치·독립 실행·정확 문서 열기

**절차:** 필요한 도구만 설치해 저장 문서로 직접 진입한다. 같은 service/document를 다시
열고 다른 저장소의 같은 ID도 연다. 미적용 입력/선택을 남겨 닫기를 취소한 뒤, 닫기를
수락하고 새 프로세스에서 같은 저장 입력을 읽는다. 결과 열기로 계산을 제출하지 않는다.

**기준:** 같은 문서는 기존 owner/PID/세션을 유지하고 다른 저장소는 구별한다. 잘못된
세션·없는 대상·미확인 연결을 중복 창으로 우회하지 않는다. native working 문서 재사용과
저장 파일을 새 편집 사본으로 여는 동작은 구분한다.

```powershell
python -m pytest tests/test_desktop_navigation.py tests/test_owner_open_guards.py tests/test_owner_probe_race_ui.py -q
```

**결과·제한:** `b0bff6e`의 Research9 Windows matrix, 별도 native Data runtime10,
FreeCAD2/ParaView2의 accepted close·새 세션 재열기를 확인했다. Data matrix는 명시 PySide
경로다. ParaView 전경 거절은 NOT_PERFORMED이며 2초 내 종료 통지 실패는 미확인으로 남긴다.
전체 OS 입력/형상 렌더 인수는 아니다. 원 manifest/실패는 CURRENT_STATE의 B8.1 기록에서
연결한다. [native Data 사용법](NATIVE_DATA_OWNER_OPEN_KO.md).
기존 native Data owner/lifecycle 검사(`tests/check_native_data_owner_windows.py`,
`tests/check_native_data_owner_lifecycle_windows.py`)는 명시된 저장 자료의 사본·설치 실행 파일과
HTTP/로컬 활성화를 사용한다. 기존 창 전환·새 작업 취소/수락·직접 `.lml` 시작을 확인하며
원 저장 파일을 변경하지 않는다. 창 캡처/닫기 이벤트만으로 전체 OS 사용성을 인수하지 않는다.

## 편집·부분저장·복구·이동 사본

**절차:** 관련 owner의 미확정 셀/붙여넣기 → 적용 전 저장 차단/취소 → 명시 적용/관련 저장
→ 한 문서 저장 실패 또는 응답 유실 → 성공 receipt 유지/실패 문서만 재시도 → 원문 보관
→ 새 프로세스에서 정확한 기준 문서 확인 후 명시 복구 순으로 확인한다.

**기준:** 원문 보관은 owner apply/save/run이 아니다. 보관/read-back 실패나 CAS 변경이면
닫기를 막는다. 성공 문서를 다시 저장하지 않으며 UNKNOWN은 같은 요청 결과부터 확인한다.
조용한 rollback이나 전체 성공 표시가 없어야 한다.

```powershell
python -m pytest tests/test_material_related_save_ui.py tests/test_material_save_recovery_ui.py tests/test_data_material_recovery_host_ui.py -q
python -m pytest tests/test_numerical_workflows_ui.py -q
```

**결과·제한:** 이동 사본 `6b1b372`는 11종과 같은 큰 묶음의 편집/저장/재복사/cold를
인수했다. 두 300초 응답 유실은 원 UUID/signature/완료 marker로 읽기 복구했으며 성능 PASS가
아니다. 10월19일 Material+DOE Plan 부분저장은 재료 1회 성공 receipt를 유지하고 실패한
Plan만 재시도해 총 2회로 종료했다. 별도 Python에서 미확정 `1e`/`2e`, Esc·Undo와 원 참조
보존을 확인했다. 독립 Numerical/Request Plan도 owner 입력에 적용하지 않은 원문을 기존
캡슐에 보관하고 새 세션에서 명시 승인 후 복구한다. 선별 회귀 6PASS, 실제 keep/cold는
각 exit0/job_empty였다. 초기 열기 실패 뒤 빈 창을 닫지 못하던 결함은 추가 4PASS로 확인했다.
같은 Astra 검토에서 남은 P1/P2는 없었다. 원 사본 177개 항목과 실제 원본 해시 비교 93파일은
구별한다. Windows OS 클립보드는 UNKNOWN이며 붙여넣기는 단위 근거로 한정한다.
관련 저장 actual04의 캡슐 응답 timeout, cold01/host01 하네스 실패는 보존했다.
Data 포함 3-owner 및 전체 B8.2 종료로 확대하지 않는다.
[이동 사본 원 실행 기록](portable_connection_c3a/WINDOWS_VERIFICATION_KO.md).

## Data·Material·Numerical

**절차:** 원행/단위/관측량 고정 → 처리·관측을 같은 Material 계획 검토로 전달 → 편집 중
보류·취소·재전달·원 대상 보호 → 수치 계획의 원 입력/결과 대조 → 저장/재열기를 확인한다.

**기준:** P와 Cauchy σ, 관측 J와 J=1 가정, 절점과 적분점, 공칭 RF/A0와 응력을 구분한다.
배경 읽기가 미확정 텍스트/선택을 바꾸면 실패다. invalid draft는 보관 가능하지만 필수
입력이 잘못되면 실행을 막는다. native Data 미적용 입력은 도구 열기 전에 적용/Undo한다.

```powershell
python -m pytest tests/test_data_companion_owner_ui.py tests/test_material_observation_owner_ui.py tests/test_owner_background_focus_ui.py tests/test_data_processing_recipe_display.py -q
```

**J2·DP:** 같은 1 mm 합성 시험의 인장/압축/구속 이력을 원 입력·허용값으로 비교한다.
J2 재료점·DP FE·CCX의 실제9계산과 실행 전 거절1건, DP64 IP/CCX27절점, 역항복/탄성 복귀를
구분한다. Post3개와 Study9참조는 새 계산 없이 재열었다. `ed6b58e`의 한정 인수이며 교차
솔버/실물 qualification은 UNKNOWN이다. [모델·측도와 원 실행](CASE_A_J2_DP_KO.md),
[구성식 전문 기록](law-native/ACCEPTANCE_KO.md)은 상세 근거로 보존한다.
기존 검사는 `tests/law_native/test_case_a_observables.py`(측도/원값),
`tests/check_case_a_retained.py`(보존 HTTP 읽기), `tests/check_case_a_inspection_windows.py`
(Material 선택 화면)를 사용한다. 원 receipt/source hash는 `_workspace/case-a-20261018/`에
보존하며 새 수정 회차용 checker를 추가하지 않는다.

## PDE·Simulation·Evaluation와 장 전달

**10월19일 선택/결과 화면 교정:** Simulation 단일 값은 가짜 그래프 축 대신 물리량·값·
단위 표에 표시한다. 화면은 유효숫자로 읽되 원값은 tooltip/결과에 그대로 남긴다.
Evaluation은 중복 단계표를 없애고 선택 단계의 원본·입출력과 계산 당시 선택 결과를
구별한다. 기존 `test_simulation_layout.py`/`test_evaluation_window.py` 등 관련 Qt 37PASS,
표시 교정 2PASS+1PASS. 같은 thermal 저장본에서 scalar↔field·미완성 편집/Cancel·명시
저장, 같은 Evaluation 저장본에서 선택 단계·전달표·Cancel·저장, 별도 Python 재개를
확인했다. 실제 series 곡선 전환은 표시용 unit 범위이며 새 thermal 계산은 하지 않았다.
원 결과·이전 revision·원 store·Jobs 불변, 소유 프로세스 job_empty. 초기 Evaluation의
busy 대기 하네스 실패는 원 로그에 보존한다. 같은 Astra가 다섯 파일과 최종 6PNG·
저장/cold 근거를 읽어 scoped P1/P2 없음으로 검토했다. 전체 GUI/공학 적합성 수용은 아니다.
근거는 `_workspace/gui-simulation-evaluation-20261019/{actual-01,actual-03,cold-01,cold-02}`와
공개 [Simulation/Evaluation 화면](SCREEN_GUIDE_KO.md#해석에서-모델-조건과-결과-확인하기)이다.

**절차:** 선언 backend/OS/profile의 편집/명시 적용 → 실행/실패/취소 → 마지막 수락 상태
선택 → 저장/재열기를 확인한다. 전달은 source 결과/기준 메시·좌표계·단위·시각과 receiver
경계를 고정해 mask/필수 DOF를 대조한다.

**기준:** 자동 검토가 새 사용자 편집을 apply하면 실패다. source/receiver 계보를 구분하고
지원되지 않는 지지나 필수 절점 누락을 실행 전에 차단한다.

```powershell
python -m pytest tests/test_evaluation_window.py tests/test_research_pde_ui.py tests/test_structural_transfer_binding.py tests/test_structural_field_transfer.py -q
```

**결과·제한:** TR-U `5216e37`은 보존 U를 다른35절점/8 C3D10에 전달해 수신1회를 실행했다.
U PASS, 절점 응력262.497 대 기준262.5 MPa는 원 엄격 허용값에서 FAIL, IP 출력 부재는
UNKNOWN이다. 기준 FCStd는 매핑된 편집 모델이 아니다.
[원 계약·실행](STRUCTURAL_U_TRANSFER_KO.md).

원 수치 확인의 입력은 `Dthermalfree`의 CCX U와 같은 10×1×1 mm 영역의 35절점/8 C3D10
수신이며 외곽 34절점 XYZ만 지정했다. E=210000 MPa, ν=0.3의 기계적 수신 기준은
`u=.0005 X`, 정상응력262.5 MPa·전단0이다. 원본의 자유 열팽창 응력0은 이 수신의 응력
기준이 아니다. 거리 `1e-10 mm`·자연좌표 `1e-12`·가중치 `1e-11`은 이 작은 직선 입력에
명시한 값이며 일반 곡면의 기본값이나 공학 보증으로 확장하지 않는다. 원 수신
`J5a04c25dc23643cf8df25191a7838cff`의 내부 절점35 U는 `[0.00125,0.000125,0.000125] mm`였다.
절점 응력 FAIL의 원 허용값은 `rel=2e-6, abs=1e-6 MPa`이며 변경하지 않았다.
`contact.dat`는 0 byte·IP print 요청 부재이므로 IP 대조는 UNKNOWN이다. 원 결과는
`runs/structural-u-transfer-20261018-05/receiver-result.json`, 별도 Python/HTTP·Runner cold는
`...-06/cold-result.json`에 있다. 같은 등록 필드의 ParaView 저장·별도 재열기는 새 Job/solver0이었다.

```powershell
python tests/check_structural_u_transfer_windows.py --prepare runs/structural-u-transfer-example
```

이 명령은 원본 읽기·선언·미리보기만 생성한다. 제품의 필수 입력이나 native 수신 실행이
아니다. 실제 native 확인은 같은 기존 checker와 `scripts/native_check.py`를 사용하며,
새 출력 폴더에서 소유 프로세스 정리까지 확인한다.

10월19일 작성 기능은 실제 원 결과 선택→3D 면 선택→변위 확인/취소/적용→미확정 원문
보호→저장→별도 FreeCAD 재열기와 입력 생성까지 확인했다. actual05와 새 배치의08은
옛 102개 BC 중 15개의 마지막 비트 차이(최대 `6.5052e-19 mm`)로 기존 strict 입력 동일성
검사의 마지막 단계가 FAIL이다. NumPy별 순수 mapper 차이는 재현했으나 직접 원인은
UNKNOWN이며 원 기준·입력·응력 FAIL을 유지한다. 새 수신 CCX07은 미실행 보류다.
08의 작은 3D 공간·빈 native 작업 overlay는 14의 실제 일반/좁은 화면에서 교정했다.
native 종료 저장 전 Model/Tasks/계산/overlay 복원과 원 편집·저장본 불변을 확인해 같은
Astra가 종료 P2를 폐쇄했다. 원14 전체 FAIL은 뒤 cleanup 호출까지 포함한 assertion 때문이며
원 receipt는 그대로 둔다. 필터만 고치기 위한 별도 native 재실행은 하지 않았다.

범용 수신의 실제15는 미리 만든 고정 조건0, 임의 native 객체 이름, 사용자가 작성한 단일
STATIC(길이2.5·증분77·출력7)에서 원 결과/프레임→실제 면 선택→확인/취소/적용→미완성 원문
보관/Undo→저장→별도 cold→기존 입력 생성까지 PASS였다. accepted U→frozen DOF와 원 단계
보존을 검사했으며 옛 INP byte 동등성 검사를 이 다른 사용자 모델의 목표로 삼지 않았다.
원15에서도 좁은 대상 이름이 잘렸으므로 그 화면 P2를 보존했고, 16에서 같은 저장본의
일반/좁은 6화면을 읽기 전용으로 확인해 교정했다. 새 source copy/solver/provider0,
Job0→0·원본/저장본 불변, 모든 소유 프로세스 exit0/job_empty였다. 구현·원 실행·UI delta의
해시와 원 PNG는 `_workspace/tr-u-authoring-20261019/`의 해당 폴더에 구별해 보존한다.
소스의 조건×DOF 부분 교체/다른 지지·힘·원 단계/곡선 보존과 실제 프레임2/step2의 local
좌표·exact pin은 전용 순수 검사 근거이며, 기존 조건 선택 모달의 native 조작이나 새 수신
solver 계산까지 확인했다고 확대하지 않는다. 같은 독립 검토의 관련 P1/P2는 없다.
17은 같은 저장본의 이름/종류/좌표 표현만 읽기 전용으로 확인했다. 사용자 Label은 유지하며
이름과 별도 실제 ‘정적 구조 해석 / CalculiX’를 표시하고, ‘대상 모델’·‘전역 좌표계’로 고쳤다.
잘못된 이름에서 유형을 추정하지 않는 static/dynamic/mixed/다단계/nonlinear/frequency·
설정 누락 반례를 포함한 UI 검사는 34PASS였다. 일반/좁은 6화면에서 해당 표시·대상 두 줄·
선택/필수 명령을 확인했다. 원본·구현·저장본 불변, 새 source-array/preview/freeze/solver/provider0,
Job0→0, 소유 outer/native exit0/job_empty다. 이 캡션 교정의 근거를 원15 기능 실행과 구분한다.
저장/복구 기능 확인이나 실제 창 캡처를 전체 GUI 품질 수용으로 기록하지 않는다.

**두 영역 열·점탄성:** 기존 `connector_code_review` 후보를 재사용하고 기존 FELUPE Hex8
worker에 한정 통합했다. 명시 CTE/Tref/물성·온도 이력과 공유 full-face 완전 접합만 허용한다.
표시된 K는 절대 온도이며 내부 상태의 유한 지연 복귀를 영구 소성으로 표시하지 않는다.

```powershell
python -m pytest tests/law_native/test_thermal_regions.py -q
```

실제 실행은 이 파일의 opt-in node와 기존 `scripts/native_check.py`를 사용한다. FE 1회는
같은 8요소 입력의 5시각×64IP 변형/응력/온도/전체·열·기계 변형률/상태·반력과 모든 응답이
보존 owner 결과와 정확히 같았다(43.39초, exit0/job_empty). GUI02는 편집·취소·Apply→Undo,
보존 상태 계속 작성의 Cancel, 잘못된 `1e`의 명시 저장과 실행 HTTP400/새 Job0, 별도 Python
cold 복구·Undo를 확인했다(107.52초, exit0/job_empty). GUI01은 placeholder를 실제 결과로
오인한 settle 하네스 실패로 보존했다. 생성 시 빈/한 행/온도 길이 불일치 6반례를 포함한
관련 순수 검사 41PASS, 빈 이력의 입력 보존·한국어 안내와 숫자 오류의 원문 tooltip을
후속 실제 창 delta 1PASS/일반·좁은 4PNG로 확인했다(22.57초, exit0/job_empty, 새 Job0).
이 생성기 guard·표시 근거는 원 FE source와 구별하며 추가 FE는 실행하지 않았다.
원 32/64요소의 곡률 오차 69.2194%/35.8396%는 8% 기준에서 모두 FAIL이고 네 번째 원 실행의
180초 timeout도 불완전이다. 원 fe05의 실제 dx 제한 부재와 최종 세 조건 helper를 혼합하지
않는다. 실물/정량 적합성은 UNKNOWN이다. 새 외부 온도 port는 연결하지 않았다.
원 입력·후보·실행·화면은 `_workspace/thermal-regions-integration-20261019/`에 보존하며,
절차와 결과를 별도 회차별 공개 acceptance 문서로 복제하지 않는다.

## Pre·Runner·Post와 외부 실행

**절차:** 실제 native 선택/조건을 기존 writer로 내보내 원 입력과 대조 → Runner 진행/실패/
취소·원 모델 복귀 → Post의 같은 field/위치/시각을 확인한다. remote 명령은 같은 token으로
재확인하고 실제 종료 확인 후 checksum을 검증해 회수한다.

**기준:** 정상 exit는 물리 적합성 PASS가 아니다. 회수 상태와 JobManager 판정·누락/실패
후보를 구분한다. local/replayed transport는 실제 SSH/Slurm/PBS 호스트 인수가 아니다.
종료 미확인 상태에서 자동 재제출/kill/회수를 하지 않는다.

```powershell
python -m pytest tests/test_remote_execution.py tests/test_remote_execution_transport.py tests/test_remote_execution_editor.py -q
```

**결과·제한:** L03 P1의 gate 전환/출력은 보존하지만 에너지·횡속도 이상은 UNKNOWN이다.
정확 .00225 s checkpoint가 없어 P2 child는 미실행이다. [원 조건·한계](IMPACT_RECLOSURE_KO.md).
B8.4.L01은 저장 Numerical Plan→immutable batch→실제 HTTP/JobManager→명시 SSH 대역으로
응답 유실/같은 token 재확인·취소·부분 회수·checksum 오류·cold를 확인했다. 회수 완료와
FAILED Job, 누락 수, 종료 미확인을 각각 표시한다. 손상된 pending 설정은 보존하고 신규
제출을 막는다. 같은 URL의 store A→B→A에서도 B 제출/기록 쓰기 0, 원 A token/인수/기록
유지 및 원 Job 확인을 포함한 영향 8PASS였다. 원 13PASS, Windows 6PASS+2 setup ERROR,
수정된 두 setup의 2PASS는 같은 전체 실행 성공으로 합치지 않는다. 검토 P2는 폐쇄했다.
외부 SSH/Slurm/PBS 호스트 인수(L02–04)는 NOT_RUN_EXTERNAL이다. 원 기록은
`_workspace/remote-workflow-20261019/`, 복구는 `_workspace/related-save-20261019/` 및
`_workspace/numerical-recovery-20261019/`에 보존한다. 공개 저장소에는 로컬 원자료를 넣지 않는다.
[PREPOST_VERIFICATION](PREPOST_VERIFICATION.md)은 날짜별 원 실행 기록으로 유지한다.

## Expert·Study·Report

**절차:** 정확한 원문 위치/보존 결과/명시 판단 → 같은 Study → Report 자산 저장 → 원
store/provider를 차단한 새 프로세스에서 같은 참조와 PDF/Markdown 읽기를 확인한다.

**기준·결과:** 출처 미확인·자료 누락·실패를 합의나 성공으로 바꾸지 않는다. 문헌만으로도
저장/보고할 수 있어야 하며 후속 Plan 작성과 실행을 구분한다. 기존 `f7de485`, `8ea3e87`,
`b184e35`, L04 `6bf7a39`의 한정 인수와 원 실패를 재사용한다.
[문헌/연구 원 기록](experiment_expert/VERIFICATION_KO.md),
[이동 문서 원 기록](portable_study_expert/VERIFICATION_KO.md).

## 예제와 검사 코드 관리

`examples/`는 사용자가 따라 할 대표 작업/입력 생성, 기능별 `tests/`는 assertion/오류 주입/
복구 검사로 구분한다. `examples/post_curves.py` 입력 생성과
`tests/check_post_curves_native.py` 검사는 역할이 달라 합치지 않는다.
`examples/assembly-candidate/native_check.py`는 기존 `tests/test_assembly_pose_cold_edit.py`가
helper를 직접 소비하므로 호출 의존을 함께 교정하기 전 이동/삭제하지 않는다. 원 실패·수치
기준·실행 기록을 지우거나 파일 재배치를 기능 완료로 표시하지 않는다.
