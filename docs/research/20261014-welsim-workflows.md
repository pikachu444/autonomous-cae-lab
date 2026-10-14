# WELSIM 작업 흐름을 우리 전후처리에 적용할 곳

확인일: 2026-10-14. 공식 문서·공식 블로그·WelSimLLC의 공개 저장소만 사용했다.
연구 스킬과 프로젝트 cae-desktop-ux의 VIS-SPACE/WIN-COMMAND/QT-PANELS/PV-VIEW를 적용했다.
설치, trial, 결제, 계정 작업, native 실행과 새 solver 계산은 하지 않았다.
WELSIM 이미지는 원격 원본을 읽기만 했고 저장소에 복사하거나 배포하지 않았다.
라이선스·공개 코드 채택 판단은 lead의 별도 조사 소유이며 이 문서는 사용자 조작 인계다.

결론은 **선택한 객체에 속성·3D·표·곡선을 연결하고, 입력 준비와 실행을 분리하는 흐름**에
기존 명령과 화면을 연결하는 것이다. WELSIM의 본체, 큰 아이콘 줄, 색상, 객체 이름을 그대로 가져오는 제안이 아니다.
우리 제품은 FreeCAD/ParaView와 독립 Qt 도구의 같은 저장 참조를 유지한다.

## 1. 직접 읽은 공식 경로와 화면

아래 S번호는 이 문서 안의 출처 약칭이다. 모든 조회일은 위 확인일이다.
문서가 설명하는 사실과 우리 제품에 적용하는 판단은 다음 절에서 구분한다.

| 출처 | 원문에서 확인한 작업·제약 |
|---|---|
| [S1 UI](https://docs.welsim.com/welsim/users/gui/) | 트리 객체를 고르면 속성·표·곡선이 갱신되고 표와 곡선은 같은 데이터다. 객체별 우클릭 메뉴, 선택 필터, geometry 선택의 OK/Cancel, 접기 가능한 패널이 있다. 파일 저장과 입력 파일 export 명령은 별개다. invalid 입력을 버릴 수 있다는 동작도 설명한다. |
| [S2 Geometry](https://docs.welsim.com/welsim/users/geometry/) | Part를 Geometry 그룹에 모으고 재료 할당, 표시/숨김과 해석 제외를 구분한다. STEP/IGES를 가져오며 STEP의 다중 Part, IGES의 surface→solid 처리와 Scale을 설명한다. CAD 파라메트릭 이력·조립 관절의 보존 증거는 아니다. |
| [S3 Connections](https://docs.welsim.com/welsim/users/connections/) | 접촉쌍의 Master/Target을 속성에서 선택하고 다른 색으로 표시한다. 접촉 종류에 따라 formulation/sliding/tolerance/penalty 옵션이 나타난다. 두 쪽 교환 조작을 제공한다. default numerical 값을 우리 접촉 법칙으로 복사할 근거는 아니다. |
| [S4 Study 설정](https://docs.welsim.com/welsim/users/study/) | 단계 수·현재 단계·증가하는 종료 시각, 비선형 수렴 제어, 선형 대수 solver, 출력 빈도를 구별한다. 단계별 설정은 별도 큰 spreadsheet로 편집한다. 고차 요소를 결과에서 선형으로 바꾸는 옵션도 있으므로 원 요소 표현과 표시를 구분해야 한다. |
| [S5 Results](https://docs.welsim.com/welsim/users/results/) | 결과 객체를 추가하고 Set Number 또는 Time/Frequency로 읽을 표본을 선택한다. 변형 배율은 표시 속성이다. 범례에 결과 종류·단위·시각을 포함하고 결과 데이터 export를 제공한다. 절점 응력을 설명하므로 우리 셀/절점 association을 암묵 변환하면 안 된다. |
| [S6 External solvers](https://docs.welsim.com/welsim/external_solvers/) | Preferences에서 solver 경로를 설정하며 solver별 전처리/후처리 지원·포함 여부를 표로 구분한다. Program Controlled의 물리별 기본 solver와 수동 선택이 있다. 이 자동 선택을 우리 버전 고정/명시 실행 정책으로 그대로 옮기지 않는다. |
| [S7 Transient 예제](https://docs.welsim.com/welsim/get_started/structural/structural_transient/) | 단위→재료→세 Part→전역/국소 메시→접촉쌍→18단계→조건→Compute→결과 종류 선택의 경로를 설명한다. FrontISTR/OpenRadioss의 연결을 설명하나 모든 transient 문제에 explicit가 적합하다는 우리 판단으로 채택하지 않는다. |
| [S8 OpenRadioss 입력 생성](https://welsim.com/2023/01/04/run-openradioss-solver-for-explicit-dynamics-analysis-using-welsim.html) | 별도 export로 Starter/Engine/mesh include를 만든다. 2023 글은 일부 요소만 지원하며 당시 미지원 history를 0으로 표시했다고 명시한다. 입력 준비/파일 확인 경로만 참고하고 0 대체는 배제한다. |
| [S9 시간 변화 조건](https://welsim.com/2023/04/28/multi_step_and_time_varying_settings_in_dynamics_simulation.html) | 단계 종료 시각과 조건 값을 table/chart로 함께 편집한다. 조건 표의 시각은 Study Settings에서 바꾸며 조건마다 독립된 시간 표를 만드는 구조가 아니다. |
| [S10 단위 흐름](https://docs.welsim.com/welsim/users/steps/) | 분석 단위계를 먼저 정하고 FEM 객체 단위는 그 기준에 고정한다. 재료의 다른 단위는 solve 시 시스템 단위로 변환한다. 자동 mesh도 설명하지만 우리 명시적 mesh 생성/세대검사를 없애지 않는다. |
| [S11 MatEditor](https://docs.welsim.com/mateditor/mat_properties/), [Radioss export](https://docs.welsim.com/mateditor/mat_io_openradioss/) | 재료 속성·곡선과 Radioss 단위계/법칙 목록을 제공한다. 문서는 export 기준을 Radioss 2022로 설명하며 역방향 script import 미지원을 명시한다. 원 card의 round trip이나 우리 법칙 지원 완료 근거가 아니다. |
| [S12 메시 품질](https://welsim.com/2026/07/20/the-mesh-of-engineering-simulation-3-element-quality.html) | aspect ratio/Jacobian 등의 서로 다른 정의·고차 요소의 샘플 위치를 논한다. 품질 contour로 위치를 확인하는 관례는 참고한다. 경험적 권장 숫자와 metric 이름을 우리 Jacobian 기준·샘플 수·허용치로 교체하지 않는다. |
| [S13 오류 안내](https://docs.welsim.com/troubleshooting/) | 결과/메시 불일치, explicit의 작은 시간 간격과 밀도, 긴 출력 경로 문제를 분리한다. 밀도는 물리 입력이므로 속도를 위해 변경하지 않고 단위/값 오류를 확인할 위치를 제시하는 데만 참고한다. |
| [S14 최신 화면](https://welsim.com/2026/04/01/welsim-2026r2-releases-with-all-new-dark-theme-gui.html), [Qt 스타일 글](https://welsim.com/2026/03/20/multi-style-interface-for-qt-based-desktop-software.html) | 공식 2026R2는 Dark 기본과 Qt 6.10/VTK 9.2를 설명한다. renderer/canvas 색은 Qt widget 색과 별도다. 우리의 Qt 6.9.1을 교체하거나 native host 전체 palette를 바꿀 필요를 입증하지 않는다. |

실제로 픽셀을 읽은 핵심 화면은 다음과 같다. 링크만 조사한 것이 아니다.

| 공식 원격 이미지 | 직접 관찰한 적용점과 반론 |
|---|---|
| [2023R3 전체 작업 화면](https://welsim.com/assets/blog/20230824/welsim_gui_windows_overview.png) | 왼쪽 선택 결과와 속성, 오른쪽 같은 시간의 table/chart 관계가 보인다. 하지만 icon 세 줄·기본 ID/Class Label·항상 열린 Output은 우리 기본 화면에서 제외한다. |
| [접촉 속성](https://docs.welsim.com/img/3_guide/ch3_guide_properties_view1.png) | Master/Target의 미선택 칸과 접촉 정의/고급 설정이 구별된다. 우리 선택 미완성은 색뿐 아니라 대상 이름/수정 행동으로 표시한다. |
| [18단계 표](https://docs.welsim.com/img/3_guide/ch2_start_ex2_study_prop.png) | 단계별 시간/서브스텝/허용치를 한 표에서 비교한다. 사진의 잘린 행 이름은 그대로 따라하지 않고 고정 이름 열·단위를 먼저 확보한다. |
| [OpenRadioss export 메뉴](https://welsim.com/assets/blog/20230130/welsim_export_openradioss.png) | 입력 export, 결과 읽기, 폴더 열기가 별개 조작이다. 준비된 입력을 독립 solver에 사용할 출구를 제공하는 데 직접 참고한다. |
| [2026R2 실제 Dark 화면](https://welsim.com/assets/blog/20260401/welsim_thermal_ss_dark.png) | 모델·상단 결과 의미·표·곡선의 관계는 유지됐으나 icon 과밀과 ID 노출도 남는다. Dark로 바꾸는 것보다 선택/작업 위계가 먼저다. |

이것은 공식 게시 이미지의 관찰이지 WELSIM 설치/실행이나 우리 사용자 수용이 아니다.
로고·아이콘·색상표·이미지를 제품 자산으로 복사하지 않는다.

## 2. 우선 적용할 8개 작업

아래는 **우리 코드에 대한 구현 제안**이다. WELSIM이 우리 요구를 이미 구현했다거나
기능 목록만으로 정확하다는 주장이 아니다. 기존 24행의 분모/상태는 [CURRENT_STATE](../../CURRENT_STATE.md)의
2026-10-14 표를 유지한다: 완료 8, 부분 12, 미구현 1, 확인 보류 3.

| 순서 | 원 작업 경로 → 바꿀 조작 | 우리 연결 지점 / 원 작업 | 개발 완료 조건 |
|---|---|---|---|
| 1 | 객체 선택→속성·모델·table/chart. 선택 대상 한 개를 가까운 제목으로 유지하고 우클릭/더블클릭을 같은 편집 명령으로 연결. body/face/edge 필터, 이름·재료별 그룹은 대상 찾기용이고 해석 제외와 화면 숨김을 분리. S1/S2 | `apps/desktop_pre/parameter_panel.py`, `research_panel.py`, `bridge.py`; `apps/research/post_window.py::_tree_selected`, `apps/desktop_post/bridge.py`. FN-10-01/FN-27-01 확인 보류 | 구속 재정렬 뒤 같은 semantic target 또는 명시 수리. 다른 원본을 둘러봐도 기존 측정 source_ref를 몰래 바꾸지 않음. 3D·원행·곡선의 선택 일치와 뒤늦은 읽기 차단 확인. |
| 2 | 메시 선택→품질→불량 위치→국소 크기 편집→명시 재생성→전후 비교. 품질 metric·샘플 위치·요소 ID를 표/분포 옆에서 읽고 해당 요소만 강조/격리. S7/S12 | `fem_edit.py::quality/_element_quality`, `fem_panel.py::read_quality/highlight_quality`, `mesh_binding.py`. FN-13-01 확인 보류, FN-13-02 완료 재사용 | 품질표와 정확 mesh hash/요소 일치. 생성 전후 ID·품질·지역 크기 비교까지 연결하고 실패/취소/stale에서 이전 메시 보존. 기존 sampling/threshold는 변경하지 않음. |
| 3 | Part→재료/구조 형식→필수 law·물성 표→단위 변환 확인. 재료명만 고르는 것으로 끝내지 말고 할당 영역·밀도·법칙과 실제 deck 값을 가까이 표시. layer가 필요하면 층 순서/두께/방향/재료 표로. S2/S10/S11 | `fem_edit.py`, `freeze_analysis.py`, `apps/research/material_window.py`, `native_material_window.py`, `caelab/impact_model.py`, `impact_damage.py`. FN-12-02/FN-17-01 부분 | 지원 element/law/영역 조합만 export·실행. Mg/mm/s와 kg 기반 입력의 밀도·질량/관성 변환 대조. 지원되지 않는 law/복합재는 저장 초안으로 유지하고 이유가 있는 실행 차단. 화면 추가만으로 벌크 손상 구현을 완료 처리하지 않음. |
| 4 | 접촉쌍→A/B 면 선택→법칙→필수 옵션→preview→적용/취소. 두 쪽 색/이름, 법선 화살표와 실제 간극을 보여 주고 swap은 별도 명령. 옵션은 solver capability에 따라 펼침. S3/S7 | `contact_panel.py`, `contact.py::snapshot/preview/apply_preview`, `freeze_contact.py`; `post_contact_dialog.py`. FN-14-01/02 부분, FN-14-03 완료 재사용 | 면 지정과 normal/gap/sliding 정책이 deck에 같은 뜻으로 전달. 형상 변경 취소는 old refs를 unresolved로 유지. pressure/force/gap/slip의 단위·부호·위치·시각을 같은 쌍으로 읽음. 없는 채널은 0이 아니라 미지원/미출력 사유. |
| 5 | 분석 종류→단계 시간 표→선택 단계 조건→시간 곡선→출력 정책. 실제 종료 시각, 증분·수렴 조건과 wall time을 구분. initial motion은 시간변화 BC와 섞지 않음. S4/S7/S9 | `apps/research/simulation_window.py`, `impact_editor.py`, `caelab/simulation_document.py`, `research_execution.py`. FN-15-01/02/FN-16-01 부분 | 자기 FE의 지원 nonlinear/implicit/explicit 경로에서 동일 단계·조건·단위를 저장/재열기. 실패 증분에서 해당 조건으로 돌아가 새 입력을 만듦. 존재하지 않는 종료 frame을 가장 가까운 frame으로 바꾸거나 보간 완료라고 표시하지 않음. |
| 6 | solver 경로/버전 확인→입력 파일 생성→입력/폴더 열기→계산 실행→실패 위치. input export와 Run을 메뉴/주명령으로 분리해 solver가 없는 때도 준비 작업을 끝냄. S6/S8/S13 | `scripts/local.ps1`, 기존 `start_cae_pre.ps1/post.ps1`, `freeze_contact.py`, `caelab/adapters/impact.py`, `opencourant_runtime.py`, `apps/research/runner_window.py`. FN-16-01/02/FN-15-02 부분, FN-25-01/02 완료 재사용 | Starter/Engine/include와 frozen 원 입력·버전이 정확히 같은 새 작업 폴더에 보존됨. 준비는 새 solver 실행을 유발하지 않음. 설치 없음/실행 실패/결과 읽기 실패를 나누고 기존 파일과 종료 미확인 프로세스를 보존. OpenRadioss 안내와 현재 OpenCourant pin을 같은 바이너리라고 자동 치환하지 않음. |
| 7 | 결과 객체→물리량·성분·단위·위치/association·시각→원표/curve→비교. 표시 배율/범례 변경은 원값과 분리. 시각/표 행 선택과 3D 강조를 같은 선택으로 연결. S1/S5 | `external.py::select_array/set_time`, `measurements.py`, `post_window.py::read_samples`, `post_measurement_dialog.py`, `apps/desktop_post/analysis.py`, `caelab/impact_results.py`, `fatigue.py`. FN-27-01 보류/FN-28-02 미구현/FN-16-02 부분 | 원 frame·node/cell·component·units를 선택/저장/전달에서 유지. 서로 다른 단위·좌표·시각·association/vector/tensor 비교는 converter/mapping 구현 후만 활성화. Applicable=0/NaN/실패를 안전0으로 대체하지 않음. 기존 scalar 비교 FN-28-01은 다시 만들지 않음. |
| 8 | 저장→닫기 선택→같은 선택 재열기→누락 섹션/파일 복구→표·곡선 내보내기/보고서. source 변경은 다른 새 분기로 명시 적용하고 과거 본문·선택은 유지. S1/S5 및 진행 중 D9 | `commands.py::save_project`, `source_repair.py::repair_source`, `post_window.py::save_document`, `desktop.py`; Study/`costorm_report.py`/D9 ReportWindow. FN-27-02/FN-28-03 부분 | native Ctrl+S/닫기와 분석 저장을 같은 owner 경로로 연결. 원 파일 내용이 달라졌으면 영향받은 측정/비교를 표시하고 명시 새 분기. PDF/MD는 적용한 selection과 값/units/quality 상태를 유지하며 실패·취소가 초안/이전 출력을 지우지 않음. D9 owner/일반 보고서를 Co-STORM report로 대신하지 않음. |

원 24행의 나머지와 범위를 빠뜨리지 않는다. FN-11-01의 복수·종속/중첩·루프 관절은
이번 WELSIM 문서의 다중 Part·접촉 화면만으로 재사용 구현을 정할 수 없다. 조립 운동
자료가 확인된 것처럼 쓰지 않고 기존 FreeCAD Motion 경로에 남긴다. FN-17-02의 다축,
변형률 수명, 평균응력/반복 소성·계면 연계도 이번 확인 자료에서 대응 workflow를 얻지
못했다. 결과 표/곡선/단위의 조작만 참고하며 S–N/rainflow 또는 물리 law 구현 근거로 사용하지 않는다.
완료된 FN-10-02/11-02/12-01/13-02/14-03/25-01/25-02/28-01은 위 연결의 기반으로
재사용하며 다시 미구현으로 세지 않는다. 이 문서는 24행의 완료 상태를 바꾸지 않는다.

## 3. 공식 예제와 AutoTests에서 가져올 수준

[WelSim-Apps](https://github.com/WelSimLLC/WelSim-Apps)의 공개 폴더는 제품 gallery와
auxiliary 앱 소개 중심이다. 직접 읽은 [demo.cpp](https://raw.githubusercontent.com/WelSimLLC/WelSim-Apps/main/demo.cpp)는
두 줄 주석뿐이다. 공개된 본체 GUI/solver 연결 source가 있다고 가정하지 않는다.

[WelSimAutoTests](https://github.com/WelSimLLC/WelSimAutoTests)에는 GUI/mesh/results,
FrontISTR/OpenRadioss/CalculiX 등의 XML 행동 자료가 있다. README는 실행에 WELSIM
라이선스와 일부 외부 solver 설정이 필요하다고 명시한다. 공개 파일의 Apache-2.0과
본체 실행 권한은 별개이며, 우리 무료 실행 harness로 설치/채택하지 않는다.
[기록 문서](https://docs.welsim.com/welsim/regression/regression_create_test/)는 wsevent의
조작과 wscheck의 값 검사를 구분한다. [재생 문서](https://docs.welsim.com/welsim/regression/regression_run_test/)는
실패 case만 다시 읽고 로그/프로젝트를 남길 수 있다고 설명한다.

직접 읽은 [13013 마찰 접촉 XML](https://raw.githubusercontent.com/WelSimLLC/WelSimAutoTests/main/13_CalculiX/13013_calculix_contact_frictional.xml)은
단위→두 박스→mesh→Master/Target 면→마찰0.5→CalculiX 선택→구속/압력→Solve 순서다.
마지막 wscheck는 FRD 파일 존재뿐이다. 이를 입력/조작 단계의 참고로 쓰고 마찰력·간극의
정확성, 일반 접촉 지원이나 우리 수치 수용 근거로 쓰지 않는다. 숫자 tree index나 widget
object-name 경로도 우리의 semantic target/late-read 토큰으로 바꾸어야 한다.

## 4. 그대로 가져오지 않을 것과 다음 인계

UI 문서의 invalid 값 버림 대신 우리 `1e`/잘못된 초안을 보존한다. 기본 강철·자동 mesh·
Program Controlled solver를 실제 사용자 입력/명시 실행으로 오해시키지 않는다.
숫자 0 history는 결측을 숨기므로 사용하지 않는다. 변형 표시 배율은 물리 형상 변경이
아니며 결과 셀→절점 평균도 별도 처리로 남긴다. WELSIM의 Study는 FEM 분석 설정이고
우리 연구 판단 Study와 다른 객체다. 이름을 그대로 붙여 저장 의미를 합치지 않는다.

독립 Qt 창은 공통 appearance를 사용하고 native FreeCAD/ParaView 전체는 패치하지 않는다.
Dark 신규 구현·새 report framework·test recorder를 이 조사 때문에 선행조건으로 만들지
않는다. UI 개선과 solver 카드/reader/물리 지원은 다른 작업이며, 새 폼을 붙여 후자를
완료 처리하지 않는다. 검증 임계값·실패·원 출력과 UNKNOWN/NOT_RELEASED를 유지한다.

다음 Pro 인계는 1/4/5/6/7의 선택→조건→입력 생성→실행→동일 결과 읽기를 한 묶음으로
작성하되 D9 동시 소유 파일을 먼저 분리한다. 2의 불량 요소 전체 흐름과 8의 native 저장/
복구는 별도 좁은 구현으로 이어갈 수 있다. 인수는 새 전체 benchmark 대신 기존 보존
모델/결과에서 같은 대상·단위·시각·취소·저장 재열기를 확인하고, 새로운 exporter/law를
추가한 부분만 해당 실제 계산을 수행한다. 조사 자체는 제품 구현·WELSIM 실행·공학 승인과 구별한다.
