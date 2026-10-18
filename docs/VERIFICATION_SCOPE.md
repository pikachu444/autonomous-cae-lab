# 기능별 검증 매뉴얼

사용은 [설치 안내](INSTALL_KO.md), [처음 시작하기](USER_GUIDE_KO.md),
[화면별 사용법](SCREEN_GUIDE_KO.md)에서 시작한다. 이 문서는 개발·검증 담당자의 현행
절차·기준·명령·결과 입구다. 현재 배정은 [CURRENT_STATE](../CURRENT_STATE.md) 한 곳에서 관리한다.

교정 회차마다 acceptance 문서나 일회성 시작 스크립트를 만들지 않는다. 검사는 기존
기능별 `tests/`와 `scripts/native_check.py`에 통합한다. 날짜별 입력·실패·출력·로그는
원 기록으로 보존하고 이 문서에서 연결한다. 파일 수를 제품 완성도로 세지 않는다.

## 검증의 구분

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
```

**결과·제한:** 이동 사본 `6b1b372`는 11종과 같은 큰 묶음의 편집/저장/재복사/cold를
인수했다. 두 300초 응답 유실은 원 UUID/signature/완료 marker로 읽기 복구했으며 성능 PASS가
아니다. B8.2의 별도 앱 부분저장·독립 Plan 원문 복구는 후속 구현 중이다. 두 문서 성공으로
Data 포함 전체 인수를 완료했다고 하지 않는다. [원 실행 기록](portable_connection_c3a/WINDOWS_VERIFICATION_KO.md).

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
UNKNOWN이다. authoring GUI는 후속 작업이고 기준 FCStd는 매핑된 편집 모델이 아니다.
[원 계약·실행](STRUCTURAL_U_TRANSFER_KO.md). 다영역 열/점탄성도 통합 중이며 원 곡률
기준 FAIL을 성공으로 바꾸지 않는다.

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
