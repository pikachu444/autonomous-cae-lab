# 충격과 손상 구현 인계

D7 Windows 후속까지 통합된 기준에서 작성한 실제 구현 인계다. 현재 전송·배정 상태는 CURRENT_STATE를 따른다.
이 파일은 배정이나 구현 완료 기록이 아니다. 현재 작업은 CURRENT_STATE를 따른다.

요청 ID: PRO-IMPACT-DAMAGE-RESEARCH-01
저장소: https://github.com/pikachu444/autonomous-cae-lab
구현 기준: main 4648d177933def7423dc7d5511952fa11e9ce459. Pro D7의 208ca13까지 통합됐고
구성식 화면 교정은 a6f7765에 있다. 이 기준에서 새 codex/ 브랜치로 D8 전체 구현을 시작한다.

사용자는 자기 모델로 충격·낙하와 손상을 연구하고 독립 프로그램에서 저장한 같은 자료를
전처리, 해석, 후처리, 수치 탐색, 연구 기록으로 이어 쓰려 한다. 정해진 강체 예제를 다시
통과하거나 입력 폼을 추가하는 것으로 일반 사용자 모델 개발을 대신하지 말라.
Windows native Qt/FreeCAD/ParaView를 재사용하며 추가 비용은 0원이다. 사용자가 자는 동안
일상적인 구현 결정을 다시 묻지 않고 이어가도록 승인했다. Pro가 복잡한 기능을 작성하고,
Codex가 통합·로컬 실행·문서를, Sol이 분리된 GUI 작업을, Astra가 독립 검토를 맡는다.

현재 분리 소유권: Sol은 scripts/install-opencourant-windows.ps1과 필요한 설치용 검사만
작성한다. 공식 무료 archive 선택 설치/오프라인 파일/기존 runtime 보존을 담당하며 adapter,
Core 또는 service 설정은 건드리지 않는다. 이 파일을 동시에 덮어쓰지 말고 그대로 연결하라.
구성식 창의 접선 축/원자료 열 배치 교정은 통합본을 재사용하며 D8에서 되돌리지 말라.

## 전체 범위와 기존 코드

원 요구는 FUNCTION_SPEC.md FN-16/17, implementation_map.csv의 D8 네 작업,
.moai/specs/SPEC-IMPACT-001/spec.md와 acceptance.md다. 네 작업 각각의 구현 상태를
반환하고, 없는 기능을 요구에서 제거하거나 모두 완료한 것처럼 표시하지 말라.

기존 경로를 먼저 읽는다:

- caelab/simulation_document.py: 같은 저장 문서, 등록 계산 방법, 편집 진단.
- apps/research/simulation_window.py와 native_material_window.py: 기존 독립 창.
  D7 통합본의 공통 PDEWindow, 실제 구성식 결과 조사 기능을 재사용한다.
- plugins/explicit_dynamics/reference.py: 강체 정육면체, 탄성 정지장치,
  selected_history의 전역 Z 가속도. 일반 회전/조립/복합재/손상 지원으로 확대 해석하지 않는다.
- caelab/adapters/openradioss.py, openradioss_worker.py, openradioss_history.py:
  native 입력/실행과 원 시간·속도 표본·에너지 읽기. 실제 사용 가능한 카드·단위·결과를 유지한다.
- 기존 FreeCAD Analysis/접촉 편집, Runner, ParaView 결과 및 측정, Numerical의 저장 모델 연결.
  별도 owner/scheduler, 유료 전처리기나 LS-OPT를 추가하지 않는다.

## 끝낼 사용자 작업

### 실제 재사용 경로를 결정한 조사

Sol/Astra가 기존 native FE 경로와 유지되는 공개 도구 소스를 읽고 직접 토론했다.
FreeCAD의 실제 `FemInputWriterCcx`, `apps/desktop_pre/freeze_analysis.py`의 mesh/sets/
재료 추출, `freeze_contact.py`의 실제 element-face sets를 재사용한다. 현재 static
freeze는 단일 solid C3D10, isotropic E/ν, Fixed/Force의 제한된 경로이며 허용 카드에
밀도가 없다. mm/N/MPa static 입력을 converter에 그대로 넣어 동적 지원이라고 하지 말라.
기존 native 자산을 재사용한 별도 explicit 정의에서 density/part/material/contact/IC/
시간 제어를 명시하고 보존한다. 원 static 계약을 완화하지 않는다.

우선 후보는 MIT INP2RAD, OpenCourant/Tools commit
`beaf8a17c880242bb7ad43325a20bd589dc0f533`,
`input_converters/inp2rad/inp2rad/inp2rad.py`다. 공개 원문은
https://github.com/OpenCourant/Tools/blob/beaf8a17c880242bb7ad43325a20bd589dc0f533/input_converters/inp2rad/inp2rad/inp2rad.py
이다. README에 C3D10/M, surface/contact/friction, velocity IC, cohesive와 JC onset이
있으며 includes는 읽고 출력은 합쳐진 한 파일이다. 옛 includes 미지원 주장은 현재와 다르다.
소스 약5611행에서 dt=5e-7, run_time=1, animation=1e-2, TH=1e-4 기본값을 쓰며,
약6217행에 Mg/mm/s를 출력한다. CLI는 --radv 2023|2025다. 원 코드 MIT 허가문을
보존하고 실제 미지원 sub-option을 확인하라. Qt에 tkinter/global상태를 합치지 말고
기존 소유 subprocess에서 호출하는 안을 우선한다. 이 경로에 실질적 결함이 있으면
원문과 사용자 작업을 근거로 반론하라. converter는 아직 실행하지 않았다.

mm/N/MPa와 Mg/mm/s의 일관성 때문에 kg질량·kg/m³밀도를 숫자 그대로 넣어서는 안 된다.
원/변환 node/element/part/material/set, density/총질량/COM/관성, 초기속도/각속도,
시간·출력 설정의 의미를 대조한다. converter의 묵시 기본값을 사용자가 정한 충격 조건으로
채택하지 않는다. 원 INP/includes와 변환 merged deck을 함께 보존한다. 높이 모드는
출발점 v=0+중력 적분과 충돌 직전 위치+유도속도를 구별하며 같은 낙하구간의 중복을 막는다.
중력 on/off만으로 초기속도 모드를 구별하지 않는다.

기존 OpenRadioss worker 약157행의 NUMNOD=9/11, BRICK1, RBODY1/node9 및 kg/m/s
제한과 history reader의 회전 거절은 원 강체 예제용이다. 이것을 느슨하게 만들지 말고
별도 일반 adapter/result reader를 기존 owner에 등록하라. 실제 part/node/element/time/
unit/frame을 읽고 기존 exact selection으로 Post/Numerical/Study에 연결한다.
공식 Tools의 `output_converters/anim_to_vtk`는 ANIM Axxx→legacy VTK 자산이다.
H3D를 ANIM으로 읽지 말고 실제 field/time/active mask를 VTU/PVD/기존등록에 연결하라.
원 `.rad` starter/engine/includes 묶음을 직접 여는 CAD 없는 경로도 보존한다.
cohesive/JC onset 지원목록은 혼합모드 진전/재닫힘/cyclic law/피로수명 지원 증명이 아니다.
이 상세 조사는 새 writer를 전부 작성하거나 고정 강체 예제만 개선하는 대안을 피하기 위한
재사용 제안이며, D8 네 작업의 범위를 줄이지 않는다.

**FN-16-01 — 자기 모델의 충격 조건을 만들고 저장하기.** 지원 FE 모델을 선택하고 물체,
질량·재료, 접촉, 기준 좌표, 초기 자세/질량중심을 확인한다. 높이와 중력에서 구한 이상화
충돌 속도와 측정된 초기 속도/각속도를 별도 모드로 다루고 중복 적용하지 않는다. 물리 시간,
출력 주기, 지원 시간 간격/CFL와 질량 조정을 편집한다. native 입력을 실제로 만들고
누락/미지원 카드는 해당 위치와 이유로 알린다. 일반 입력이 기존 기준 예제와 다르면
독립된 명시적 adapter 경로로 지원하고 원 예제 허용값을 넓혀 대신하지 않는다.

**FN-16-02 — 실제 충격 결과와 실패를 읽고 넘기기.** 저장 실행을 골라 원 물리 시간,
시간 간격, 추가 질량, 운동/내부/접촉/hourglass 에너지와 실제 힘·가속도 채널을 읽는다.
반 시간 간격 속도와 정시각 출력의 의미를 보존한다. 변형/실패 위치와 부분 결과를 표시하고
원 결과를 Post/Study로 넘긴다. 필터나 peak/event 정의는 사용자가 정한 별도 처리로 저장한다.
없는 채널을 이상화 식으로 채워 native 결과라고 표시하지 않는다.

**FN-17-01 — 벌크와 계면 손상을 구분해 실행하고 비교하기.** 지원하는 실제 법칙·요소·
exporter를 선택한다. 강성, 강도, 파괴에너지, mixed mode, onset/evolution, 압축 전달과
재닫힘/마찰을 해당 단위로 편집한다. 벌크 소성과 계면 손상의 중복을 피하고 opening,
slip, damage, 에너지와 원 mesh/마스크를 읽는다. 계산 실패와 물리 파손을 구별한다.
무료 native 구현 경로를 조사해 실제 코드를 연결하며 선언/문서만으로 끝내지 않는다.

**FN-17-02 — 반복 효과와 수명 가정을 분리하기.** 실제 지원 cyclic law/누적 규칙과
시험 조건·보정 범위를 드러내고 계산한다. 데이터가 없는 경우 UNKNOWN을 유지한다.
한 cycle이나 단조 손상 결과를 피로 수명으로 바꾸지 않는다. 필요한 미구현 법칙과 자료는
구체적인 잔여로 남기되 편집·저장·독립 문서 사용까지 막지는 않는다.

## 화면, 통합, 인도

### Windows 구현에 사용할 실제 준비 환경

root가 공식 OpenCourant latest-20261011의 OpenCourant_win64.zip을 별도로 내려받고
게시 digest와 일치를 확인해 추출했다. 기존 Linux/runtime/profile은 변경하지 않았다.
Windows root는 %LOCALAPPDATA%\AutonomousCAELab\runtimes\opencourant-windows-20261011\OpenCourant.
archive SHA256=6d0ea8b43b68aa12f0a2787b339384a554978cbb65a5d3dbaf1e40598f02e7e6,
source tag cb760c206e346eff12161a2268b134ef9d48a4ef다. Windows Starter와 Engine의
`-version`은 각각 exit0, Oct11 build/win64를 반환했다. 이것은 model solve/변환기/제품
adapter 실행 완료가 아니다. root는 반환값에 CommitID가 User Build인 점도 보존했다.

기존runtime()과 같은 config hash 방식(정렬된 파일의 root상대POSIX경로bytes + fileSHAbytes)의
hm_cfg_files digest는 0cb6bcfa32474a76e2ad322cd2ea1c68a1c85821c0ff88b8e5e47723beb18fdf.
실행파일은 exec/starter_win64.exe, engine_win64.exe, anim_to_vtk_win64.exe,
th_to_csv_win64.exe다. child PATH에 extlib/hm_reader/win64, extlib/h3d/lib/win64,
extlib/intelOneAPI_runtime/win64를 추가하고 RAD_CFG_PATH, RAD_H3D_PATH,
OPENCOURANT_PATH, KMP_STACKSIZE=400m, OMP_NUM_THREADS=2를 사용했다.
전역 PATH/레지스트리/서비스는 바꾸지 않았다. owned_tree=True의 기존 Windows Job
취소 경로를 재사용하고 POSIX RLIMIT이 적용된다고 기록하지 말라.

원 COPYRIGHT/licenses/Intel runtime notice를 그대로 보존했다. HM Reader/H3D는
OpenRadioss와의 사용에 한정한 별도 허가이며 모든 번들 DLL을 AGPL로 재분류하지 않는다.
우리 제품에 새 바이너리를 묶어 배포한 것이 아니라 공식 배포 그대로 로컬 실행한다.
기본 설치가 solver를 필수로 삼지 않게 하고, Windows runtime의 명시적 선택과
별도 무료 설치/오프라인 archive 이용 경로를 기존 설치 안내/스크립트와 연결하라.
Local runtime 관측은 전달 자료이며 당신의 호스트에 같은 경로가 있다고 가정하지 말라.

### 확인한 로컬 실행 조건

현재 `scripts/local.ps1`의 Ubuntu WSL 선택은
`/home/pikachu444/.local/share/autonomous-cae-lab/opencourant-latest-20261006/OpenCourant`다.
여기서 `exec/starter_linux64_gf`, `exec/engine_linux64_gf`,
`exec/anim_to_vtk_linux64_gf`, `exec/th_to_csv_linux64_gf`의 파일/실행 권한을 확인했다.
parent의 archive, hm_cfg_files, hm_reader/h3d 라이브러리도 있다. 이번 조사는 새
version/solver/converter 실행을 하지 않았으며 기존 runtime()의 실제 pin 검사는 유지한다.
코드 선언 source는33e685176cccf0c539a3ce07aa2096985a284e2a지만 그것만으로
설치 바이너리 버전을 확인했다고 하지 않는다.

이전 `openradioss-latest-20260728/OpenRadioss`도 있으나 변환기 파일에는 실행 권한이 없다.
기존 공개 Jul28 version 로그는 그 이전 OpenRadioss의 기록이며 현재 OpenCourant 증거가
아니다. 배포가 다른 실행파일을 이름만 바꿔 자동 대체하지 말라. Windows Python receipt는
Python/Qt 설치 근거이며 그 선택 runtime의 exec/bin에는 native win64 실행파일이 없다.
Windows Qt→기존 WSL 서비스→소유 child의 Linux 실행 경로는 선택 경로로 재사용한다.
최신 사용자 지시(2026-10-14): WSL을 쓸 수 없는 PC도 대비한다. Windows native 실행도
이번 구현 요구다. 공식 https://github.com/OpenCourant/OpenCourant/releases/tag/latest-20261011
에는 OpenCourant_win64.zip과 Intel runtime 번들 안내가 있다. Linux 전용 파일명·환경
변수·프로세스 종료·경로 처리를 Windows에 그대로 복사하지 말고 Starter/Engine 및
변환기 선택을 분리한다. AGPL-3.0과 reader/H3D/Intel의 개별 허가문을 유지한다.
공식 배포 확인만 했으며 로컬 설치/Windows native 계산 완료는 아니다. WSL 없이 실제
작은 모델의 계산→결과 읽기를 완료 조건으로 포함하고 편집/저장만으로 대체하지 말라.
기존 실행 중인 서비스나 store는 몰래 바꾸지 않는다. 추가 비용이나 새 설치를 먼저
요구하지 말고 실제 adapter와 converter 호출에 필요한 경우만 확인한다.

물체/조건/그래프/결과가 중심인 실제 작업 화면을 만든다. 내부 ID, JSON, 해시, 긴
설명문을 주 작업 영역에 나열하지 않는다. 기존 source 원본과 현재 편집본·과거 결과를
구분하고 한글 메뉴, 수치 단위, 선택 상태, 미저장/오류/취소/재열기를 유지한다.
일반 상용 공학 프로그램처럼 다음 행동을 쉽게 찾게 하되 고유 native 기능을 재구현하지 않는다.

의미 있는 단위로 코드·관련 검사·짧은 한국어 예제를 인도한다. 실제 실행환경은 그때
Codex가 확인한 경로를 제공하며 저장소 pin을 설치 증명으로 쓰지 않는다. 신규 지원 행동의
작은 실행/단위 확인만 우선하고 기존 전체 벤치마크 반복으로 기능 구현을 멈추지 않는다.
실행 성공·제품 사용 가능·공학적 수용을 구별한다. 기존 실패와 수치 기준은 보존한다.
독립 사용→저장→다른 도구에서 같은 선택 열기→다시 시작의 연결을 코드로 완결한다.
변경된 기능, 실행/미실행 범위, 네 작업의 남은 항목, 적용 가능한 소스와 선택 이유를 반환한다.

### 확인한 Windows 파일 목록

{
  "exec/starter_win64.exe": "606b8d9785bb79305ede5e1467fff6e07331678ae619fe9d4e118df6c5c1309e",
  "exec/engine_win64.exe": "7530cba04c5e73fa93167496d5e11476318084c84fff9c6b0dfccc35267a81a9",
  "exec/anim_to_vtk_win64.exe": "238278b91341168f517eb1547efdb249705af8080cd1f0beca0ba61d3bc65e12",
  "exec/th_to_csv_win64.exe": "ad5b8a76b5a13aa695616f15af400ad1ea344a1afb37a2480f17aaa0ec758d01",
  "extlib/hm_reader/win64/hm_reader_win64.dll": "54dea015c6e776b9f5519bb8a31ae2f5a8fe506315e9ea393cee439c9dc869c1",
  "extlib/hm_reader/win64/libapr-1.dll": "a165557741cd95d899a9af74dd2794850772e8ecb882b353e5a0f8e5317f2720",
  "extlib/h3d/lib/win64/h3dreader.dll": "b3de1e636d2c290a8c2e95f50a6dff7036af03cb8dfae62522f986d994e01836",
  "extlib/h3d/lib/win64/h3dwriter.dll": "cbe2ef4362095e1d952d17b69c0f6a023c830500595ce00d137365f7f741e483",
  "extlib/intelOneAPI_runtime/win64/impi.dll": "9cb6ee5a55b63fd22d3cd53c1bed93ad245dc0f87701bc167b6d431384f7ed89",
  "extlib/intelOneAPI_runtime/win64/libfabric.dll": "387e2faa96209ce5e94a5dbf6f1213fc9d81da674a4e170a30e7cf2b100d56ab",
  "extlib/intelOneAPI_runtime/win64/libiomp5md.dll": "f608eedb25e44de3db1d3db984ac113f3a8406a92ea87061a77f390852fe1174",
  "extlib/intelOneAPI_runtime/win64/libmmd.dll": "e2b0066f3f4479439d5f008c74482b78ed13203d62c2ecb480cc12b4d78a01fa",
  "extlib/intelOneAPI_runtime/win64/mkl_avx2.2.dll": "95a24cf1c3df05ac7a126c09c74a3d077be0743f2036af4a934e1f2a3850d66f",
  "extlib/intelOneAPI_runtime/win64/mkl_avx512.2.dll": "ec81d74d6d1102147ade9b4f4f1a27fd122d96771b4bd80dccb5fcdde05ff304",
  "extlib/intelOneAPI_runtime/win64/mkl_core.2.dll": "2c1c53445e9ec21a04d479107a03356fb3184422c851376d1d7438164a6f46ef",
  "extlib/intelOneAPI_runtime/win64/mkl_def.2.dll": "da9cb9af9aaea16fa03539524fd599bef7eea9d4504c99d4995323b05a09004a",
  "extlib/intelOneAPI_runtime/win64/mkl_intel_thread.2.dll": "0c8856befc20b72d18e4a712f842c2e528ab77255af27abafa18595d945eabe3",
  "extlib/intelOneAPI_runtime/win64/svml_dispmd.dll": "415dbc87ff6328fa45b69ca25a5861e5e25f50b348df67590abb99839efb9a90"
}

