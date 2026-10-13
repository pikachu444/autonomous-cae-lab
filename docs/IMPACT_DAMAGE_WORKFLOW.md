# 사용자 FE 충격·손상 연구

## 현재 인도 범위

이 브랜치는 D8 구현 중간 인도입니다. FN16/17 전체 완료나 공학적 승인이 아닙니다.
작성 환경의 Python/Qt/FreeCAD/OpenCourant 실행은 **NOT_RUN**입니다.
Windows runtime 버전 확인은 Codex가 전달한 별도 근거이며 이 소스의 실행 근거가 아닙니다.

기존 고정 explicit.openradioss 모델과 원 검사 기준은 유지합니다.
새 explicit.opencourant.model은 사용자가 선택한 평탄화 FE 메시를 기존 Simulation 문서,
JobManager, 결과 보존, Numerical의 선언 입력 바인딩으로 실행합니다.

## 사용자 작업

1. 독립 해석 창에서 **새 해석 모델 → 사용자 FE 충격 (OpenCourant)** 를 선택합니다.
2. **연구 → 충격 조건… → 유한요소 파일 열기…** 에서 자신의 평탄화 INP를 고릅니다.
   단위 Mg/mm/s/N/MPa를 직접 확인합니다. 가져오기는 계산을 실행하지 않습니다.
   C3D4, C3D8/R, C3D10 및 명시 COH3D8, 등방 탄성/단조 소성, 밀도, 고정 병진 구속,
   정확한 요소 면 집합을 지원합니다. 미지원 카드·include·온도 의존·이방성은 거절하며
   원 파일을 수정하지 않습니다.
3. **초기 운동**에서 절점 집합을 추가해 병진 속도, 각속도, 회전 중심과 초기 위치를 입력합니다.
   각속도는 rad/s이며 초기 절점 속도 v+ω×r로 반영합니다.
   '높이에서 놓기'는 병진 속도 0에서 중력 반대 방향으로 시작 위치를 옮깁니다.
   비영 속도가 있으면 방식 전환 시 0으로 바꿀지 직접 확인하며 취소하면 원 속도와 방식을 보존합니다.
   '높이를 충돌 속도로 환산'은 시작 위치를 옮기지 않고 sqrt(2gh)를 적용합니다.
   두 경우 중력 방향·크기가 필수입니다. 높이와 속도를 몰래 중복하지 않습니다.
4. **접촉**에서 면 A/B와 TYPE24, 마찰계수를 명시합니다.
   원 정적 접촉의 Kn/Kstick을 같은 법칙으로 바꾸지 않습니다.
   TET10 접촉은 corner facet이며 곡면의 이차 보간 접촉이라는 주장은 하지 않습니다.
5. **시간과 중력**에서 물리 종료 시간, 장/이력 간격, 절점 증분 계수를 정합니다.
   질량 스케일링은 명시 선택이며 기본은 끔입니다. 변환기 기본 CST 증분은 실행에 쓰지 않습니다.
6. **편집 반영 → 적용 → 저장** 후 **계산**을 눌렀을 때만 Starter/Engine을 실행합니다.
   잘못된 숫자 초안은 저장할 수 있지만 실행은 막힙니다.
7. **충격 조건… → 결과 이력**에서 원 절점/요소와 성분을 추가합니다.
   실제 변위·속도·가속도·응력·접촉력과 응집 손상을 고릅니다. 원 메시 번호는 위치 선택에 쓰며
   문서 UUID와 해시는 기본 화면에 표시하지 않습니다.
   결과에서 선택 이력이나 실제 에너지/질량을 고르고 기존 **Post**로 등록된 native 장을 엽니다.
   원 메시와 결과의 시간·절점/요소 ID, 원 ANIM/T01/CSV, 비유한 값과 적용 마스크를 보존합니다.
   CYCLE=0은 변환기의 상수이므로 solver cycle로 표시하지 않습니다.
8. 기존 **수치 연구**로 명시한 초기 운동의 후보를 만들 수 있습니다.
   모델 원본과 Plan 탐색 범위는 별개이며 선택만으로 원본에 적용하지 않습니다.
   Study/Expert는 기존 정확한 문서·job 결과 참조를 사용합니다. 읽기와 전달은 계산하지 않습니다.

FreeCAD에서는 기존 연결 패널의 **충격 해석…** 로 현재 Analysis를 보존하고 해석 문서를 만듭니다.
물체별 C3D10 메시, 명시 밀도·등방 재료, Fixed와 적용된 면 집합을 추출합니다.
기존 mesh binding/품질/면 참조 검사를 통과해야 하며 coincident node를 합치지 않습니다.
정적 Force/Displacement 등 아직 동적 매핑이 없는 조건은 이름을 알려 거절합니다.
원 접촉 면은 전달하지만 동적 법칙은 사용자가 별도로 선택해야 합니다.
원 .caepre 저장과 문서 소유권은 기존 native owner가 유지합니다.

## 실행 환경과 작은 공개 예제

Windows는 기존 private Python/Qt와 별도 공식 OpenCourant runtime을 사용합니다.
기본 위치는 LOCALAPPDATA/AutonomousCAELab/runtimes/opencourant-windows-20261011/OpenCourant입니다.
운영자가 선택한 CAELAB_OPENCOURANT_ROOT(또는 기존 CAELAB_OPENRADIOSS_ROOT)도 정확한 pin으로 검사합니다.
설치 스크립트는 Sol 소유 scripts/install-opencourant-windows.ps1와 연계합니다.
이 브랜치는 자동 다운로드·WSL 전환·전역 환경 변경을 하지 않습니다.
Linux는 기존 검증된 runtime() 경로를 재사용하며 변환기 실행 가능 여부를 별도로 확인합니다.

기존 서비스 URL에 공개 합성 변형체 입력을 **저장만** 하려면:

```powershell
python -m examples.impact.user_model --service http://127.0.0.1:18767
Start-CAE-Lab.cmd -Tool simulation -DocumentId <출력된 문서> -Port 18767 -Store <같은 저장소>
```

실제 실행은 창의 계산 또는 예제의 명시 --run으로 제출합니다. 출력 ID는 복사할 때만 필요하며
주 작업 화면에서는 문서명·모델·값·단위를 사용합니다. 기존 서비스의 정확한 Store/Port를 유지하세요.

변경 경로 검사(작성자 실행 NOT_RUN):

```powershell
python -m pytest tests/test_impact_model.py tests/test_impact_results.py tests/test_impact_editor.py -q
$env:CAELAB_RUN_USER_IMPACT='1'
python -m pytest tests/test_impact_model.py -k installed_user_fe -q
```

첫 명령은 실제 pinned Python 변환기, 소유자 저장/재열기, 로컬 Qt 편집과 reader 단위 경로입니다.
두 번째는 기존 runtime에서 작은 실제 변형체 Starter/Engine/Post를 실행하므로 명시 opt-in입니다.
원 solver 캠페인의 재실행은 필요 없습니다.

## 구현 선택과 보호 경계

- INP2RAD MIT 소스 beaf8a17c880242bb7ad43325a20bd589dc0f533를 고정해 재사용합니다.
  원 CLI의 pause/실패 exit0 문제는 owned child wrapper로 처리합니다.
  tkinter만 optional import로 수정하고 원 고지와 출처를 보존했습니다.
- 입력 카드와 하위 옵션을 검사한 뒤 변환합니다. raw 변환 deck과 실제 적용 engine deck을 둘 다 보존합니다.
  Node/ordered connectivity뿐 아니라 요소별 part/material/property, 밀도·탄성/소성 표,
  고정 자유도, 명시 초기속도와 방향 있는 접촉면을 독립적으로 대조합니다.
  중복 NSET/ELSET은 원 선언의 합집합을 한 번만 내보냅니다.
  원 변환기의 GRAV는 실제 실행본에서 전역 X/Y/Z 성분 카드로 교체해 중복/방향 손실을 막습니다.
  원 변환본과 유효 deck은 별도로 보존합니다. Starter의 Mg/mm/s 선언과 SI 환산계수도 함께 검사합니다.
  effective SOLID24 / Itetra4=3 / Itetra10=2 / distortion control=1을 기록하며
  원 Abaqus 요소의 integration formulation과 동등하다고 주장하지 않습니다.
- Windows는 기존 owned_tree=True Job 제어를 사용합니다. 다른 서비스나 프로세스 이름을 종료하지 않습니다.
  취소 뒤 추가 변환 프로세스를 실행하지 않고 원 partial 파일을 남깁니다.
- Post는 기존 immutable native input registrar를 사용합니다. 별도 결과 store는 없습니다.
  새 공통 접점은 research_execution.publish_fields의 contained/hash-checked post_artifacts뿐입니다.
- 기존 separate_meshes의 기본 최소 물체수 2는 그대로이고, explicit collector만
  minimum_bodies=1을 명시합니다. 기존 접촉 검사와 solver admission을 완화하지 않습니다.
- 공식 ANIM 변환기와 th_to_csv는 release executable hash로 고정됩니다.
  release workflow가 Tools ref를 고정하지 않으므로 Python 소스 pin과 native binary source identity를 혼동하지 않습니다.
  기존 AGPL/HM Reader/H3D/Intel의 각각 다른 허가문은 설치본에 그대로 유지합니다.

## 응집 손상: 직접 만든 요소와 법칙

**충격 조건… → 응집 손상**은 가져온 COH3D8의 재료별로 법칙을 편집합니다.
벌크와 독립된 양의 두께 응집 요소, 일대일 대응하는 평면 두 면만 지원합니다.

1. INP에서 COH3D8, COHESIVE SECTION, 명시 traction 탄성 재료를 사용합니다.
   현재 가져오기 계약은 EN, ET, ET [MPa/mm], 0의 네 값입니다. 마지막 0은 온도 의존을
   적용하지 않는 변환기 입력입니다. 임의의 constitutive thickness로 강성을 나누지 않습니다.
2. 법선/전단 강도 [MPa], 모드 I/II 에너지 [N/mm], POWER 또는 BK, 해당 지수와 소실 적분점
   수를 직접 입력합니다. EN/ET는 원 재료에서 읽습니다. GI/GII는 **탄성 구간을 포함한**
   traction–separation 총 에너지입니다.
3. 원 변환기의 LAW59와 재료·part·TYPE43 적용 범위를 확인한 뒤 이 재료 카드만 LAW117로
   바꿉니다. 원 converted deck은 보존합니다. 밀도는 Imass=2 체적 밀도 [Mg/mm³]입니다.
   탄성 삼각형보다 작은 파괴 에너지는 실행 전에 거절해 Starter의 자동 계수 수정을 막습니다.
4. 재닫힘이 필요하면 **접촉**에서 반대편 벌크 면 두 집합을 TYPE24로 직접 선택합니다.
   삭제된 응집 요소를 다시 붙이거나 접촉쌍을 자동 생성하지 않습니다. 접촉의 실제 작동은
   별도 native 확인 범위입니다.
5. **결과 이력**에서 응집 요소를 골라 손상·법선 분리 변화·접선 변화를 선택합니다.

3DELEM_Damage는 native LAW117의 적분점 평균 손상입니다.
3DELEM_MAX_DAMAGE_ELEMENT와 다른 출력이며 이름을 서로 바꾸지 않습니다.
분리/접선 변화는 현재 ANIM 좌표에서 실제 초기 대응 절점 간 차이를 빼고 **고정 초기 면 기준계**로
투영한 네 쌍 평균입니다. 큰 회전에서 native corotational 적분점 opening과 같다는 주장을 하지 않습니다.
ANIM 좌표는 이미 현재 좌표이므로 Displacement를 다시 더하지 않습니다.
소실된 요소는 응답 이력에 이유와 누락으로 남고 활성 물리 Post 셀에서는 제외합니다.
원 VTK의 값·소실 상태와 제거된 셀 목록은 그대로 보존됩니다.

공개 합성 시편을 저장하고 창에서 편집하려면:

    python -m examples.impact.cohesive_model --service http://127.0.0.1:18767

이는 원본 사용자 메시를 지원하는 코드의 작은 예제이며 보정된 재료 자료나 강도 정답이 아닙니다.
--run을 명시했을 때만 실제 Starter/Engine을 제출합니다.

## 접촉력과 표본 충격량

**결과 이력 → 절점 접촉력**은 정확한 원 NODE_ID의 Contact_Forces X/Y/Z를 읽습니다.
단위는 N, 전역 Cartesian 부호를 그대로 유지합니다. 한 절점에 조립된 모든 접촉의 힘이며
선택 접촉쌍만의 힘·표면 법선력이라고 표시하지 않습니다.

**접촉력 표본 적분**은 동일 성분의 실제 출력 시각 사이를 사다리꼴 적분한 N·s입니다.
첫 출력의 0은 적분 기준이며 native impulse 관측값이 아닙니다.
중간 표본이 없으면 뒤 적분도 미정으로 남습니다. 출력 간격 사이 힘의 최대값·solver step
충격량을 복원하거나 누락 프레임을 보간하지 않습니다.

선택 이력의 물리량·단위·성분·원 위치·프레임은 기존 retained response에 함께 저장하므로
Numerical의 명시 응답/축약 선택과 Study의 정확한 결과 읽기에 그대로 사용합니다.

## 반복하중: 저장 응력 → 사이클 → 누적값

이 경로는 **Windows Python만으로** 실행합니다. OpenCourant/WSL/AI가 필요하지 않습니다.

1. Data에서 CSV의 시간 [s]과 **부호 있는 한 위치의 수직 응력** [Pa/MPa]을 매핑합니다.
   xx/yy/zz, 응력 측도, 고정 기준계, 위치를 명시한 뒤 읽고 저장합니다.
   기존 계산에서 보존한 같은 종류의 응력 이력도 선택할 수 있습니다.
2. 해석 창의 **새 해석 모델 → 반복하중과 S–N 누적**을 선택합니다.
3. **연구 → 반복하중 조건… → 응력 이력 선택…**에서 실제 보존 문서·계산·응답을 고릅니다.
   원 곡선을 읽는 동안 새 계산을 만들지 않습니다. 취소하면 원 초안은 변하지 않습니다.
4. S–N 시험점을 진폭 증가/수명 감소 순서로 입력합니다. 자료 출처, 재료·환경 조건,
   허용 평균응력 범위, 시험 온도 범위와 이력 평가 온도를 직접 지정합니다.
   log 진폭–log 수명 보간만 사용하며 외삽·Goodman 보정·부호 없는 등가응력 환산은 하지 않습니다.
5. **편집 반영 → 적용 → 저장 → 계산**으로 기존 JobManager에 평가를 명시 제출합니다.
   미완성 입력은 저장할 수 있으나 계산은 차단됩니다. 누락·제외 구간을 붙여 새 사이클을 만들지 않습니다.
6. **연구 → 사이클과 누적값…**에서 진폭·평균·반/전체 사이클·원 시간 범위·시험 수명·누적 증가를 읽습니다.
   행을 고르면 원 응력 곡선의 시작/끝 표본이 함께 표시됩니다.
   많은 사이클은 페이지로 읽으며 원 결과는 전부 보존합니다.
7. 시험 범위 밖 사이클은 이유와 UNKNOWN을 남깁니다. 부분 합과 전체 Miner 누적값은 구분합니다.
   모든 사이클이 허용될 때만 전체값을 표시합니다.
8. **선택한 닫힌 이력을 반복 블록으로 가정**은 별도 사용자 선택입니다.
   같은 전역 극값에서 시작·끝나는 닫힌 이력과 짝지어진 반사이클에 한해 가정한 D=1 블록 수를
   표시합니다. 유한 이력에서 자동으로 수명을 주장하지 않습니다.
9. 저장 후 같은 문서를 다시 열고 원 응력/사이클/누적값을 읽습니다.
   기존 Study 연결은 canonical 결과 참조를 쓰며 보고·재열기만으로 재계산하지 않습니다.

공개 합성 CSV를 Data로 읽고 반복하중 문서를 저장하는 예제:

    python -m examples.impact.fatigue_example --service http://127.0.0.1:18767

--run은 실제 rainflow/S–N 평가만 제출하며 native solver를 실행하지 않습니다.
예제 S–N 표는 **합성 시연값**이고 시험으로 확보한 재료 수명 자료가 아닙니다.
선택한 source의 정확한 문서/job/입력·결과 hash는 내부에서 재확인합니다.
공개 draft에 임의 원 결과 JSON을 넣어 그 검사를 우회할 수 없습니다.

## 네 작업과 잔여

| 작업 | 현재 작성한 연결 | 여전히 남은 기능/수용 |
|---|---|---|
| FN-16-01 초기조건·실행 | 사용자 FE import/native capture, 병진·spin·두 높이 방식, TYPE24, 시간·질량 scaling, owned 실행과 native 물리 admission | Engine/Post 실제 실행 확인, 자동 COM/관성, 일반 INCLUDE/native RAD 등록, 더 넓은 동적 하중/법칙 |
| FN-16-02 결과 판단·연결 | 실제 global 에너지/질량, 선택 위치의 변위·속도·가속도·응력·접촉력, 명시 표본 충격량, raw/mask Post, Numerical/Study/저장 | 접촉쌍별 힘·정확 solver-step impulse, 취소/실패 raw의 명시 재후처리, balance/sensitivity 비교와 공학 판단 |
| FN-17-01 손상·재닫힘 | 사용자 COH3D8/LAW117 작성·검사·실행 연결, native 손상/파생 분리·접선 이력, 명시 벌크 TYPE24 재접촉 선택 | 새 LAW117의 실제 native 실행/재닫힘 확인, JC/다른 벌크 손상, 요소별 분산 에너지, mesh objectivity/물성 보정 |
| FN-17-02 반복·수명 | 정확한 보존 단축 응력 → 실제 MIT rainflow → 시험 범위별 S–N/Miner, 선택 곡선/사이클, 저장/Study/재열기 | 실제 창·owner 실행 확인, 다축·일반 ε–N/평균응력 보정, 사이클 의존 소성/응집 피로의 실제 연성 |

새 engine/store/controller를 만들지 않았습니다. FN17 반복하중은 기존 Simulation backend 하나와
research_execution.run_domain의 정확한 source 읽기 접점만 추가합니다. 원본의 보존 결과를
해석 adapter 생성자에 전달하며, 공개 설정에 신뢰되지 않는 별도 payload를 섞지 않습니다.

rainflow 3.2.0의 실제 MIT 구현(5fc6822fd1c626739c6f95d9b4595ee80330b4fc)을 변경 없이 재사용하고
LICENSE/NOTICE를 함께 포함합니다. 새 pip 패키지나 유료 경로가 필요하지 않습니다.
공식 OpenCourant의 [LAW117 정의](https://github.com/OpenCourant/OpenCourant/blob/cb760c206e346eff12161a2268b134ef9d48a4ef/hm_cfg_files/config/CFG/radioss2022/MAT/mat117.cfg),
[실제 초기화](https://github.com/OpenCourant/OpenCourant/blob/cb760c206e346eff12161a2268b134ef9d48a4ef/starter/source/materials/mat/mat117/hm_read_mat117.F90),
[ANIM 출력](https://github.com/OpenCourant/OpenCourant/blob/cb760c206e346eff12161a2268b134ef9d48a4ef/engine/source/output/anim/generate/genani.F)을 읽어
작은 writer/reader를 작성했습니다. 해당 CFG 코드를 복사하거나 라이선스를 MIT로 바꾸지 않았습니다.

## 교정 인도와 실행 구분

Codex가 cfdb9639의 Windows 기본 경로 7통과/1실패/1native skip 및 실제 Starter 정상종료,
0오류/0경고를 전달했습니다. 당시 Engine은 단위 문자열 검사에서 차단되었으므로
Engine/Post 성공은 아직 아닙니다. 이번 교정 소스의 작성자 실행은 NOT_RUN입니다.

초기 운동 표에서 집합·방식·높이를 고르고, 아래 XYZ 네 행에서 병진·각속도·중심·위치 이동을
편집합니다. 작은 창에서도 ΔZ를 가로 스크롤 없이 수정합니다. 원문/내부 출처는
원본의 **원문과 출처…** 에 있습니다. 값 정밀도와 미완성 숫자 초안은 유지합니다.

에너지 이력의 비유한 행은 원 토큰과 quality를 남기고 그래프 구간을 끊습니다.
비활성/해당 없는 native 장은 등록 Post에 NaN으로 보내며 원 VTK의 실제 값은 그대로 보존합니다.
PVD와 모든 VTU의 hash를 등록 전후 확인합니다. 원 ELEMENT_ID와 해당 요소의 연결을 대조한 뒤
입력 part 역매핑은 별도 SourcePartID로 표시하며, converter PART_ID=0을 진짜 part라고 해석하지 않습니다.


### 이번 소스 교정의 실제 근거

Root가 e8610b7에서 **14 passed / 1 native skipped**를 보고했습니다.
실제 Windows Starter는 mandatory header 누락으로 실패했고 Engine은 시작하지 않았습니다.
새 global_gravity는 semantic reader로 파일 전체를 재직렬화하지 않습니다.
수정하는 GRAV 범위만 교체하고 최초 #RADIOSS STARTER, 단위 카드와 나머지 원문을 보존합니다.
TYPE24의 정확한 100자 행과 friction 필드 폭을 교정했고 실제 pinned converter에서
접촉 하나를 만든 뒤 전체 admission까지 가는 검사를 추가했습니다.

이번 추가 코드·Qt·새 LAW117/rainflow owner 실행의 **작성자 결과는 NOT_RUN**입니다.
JavaScript에서 문자열/괄호 균형을 확인한 것은 Python compile/test의 대체가 아닙니다.
Root의 앞선 Windows 실행과 독립 소스 검토를 작성자의 실행이라고 합치지 않습니다.

기본 변경 경로:

    python -m pytest tests/test_impact_model.py tests/test_impact_results.py tests/test_impact_damage.py tests/test_impact_editor.py tests/test_fatigue_workflow.py tests/test_fatigue_editor.py -q

LAW117 실제 native 경로가 필요할 때만 별도 명시 opt-in:

    $env:CAELAB_RUN_COHESIVE_IMPACT='1'
    python -m pytest tests/test_impact_damage.py -k installed_cohesive -q

이 명령은 새로 지원한 한 작은 합성 시편의 실행 경로 확인이며 전체 solver 캠페인이 아닙니다.
먼저 기존 CAELAB_RUN_USER_IMPACT 경로의 필수 header 교정을 확인할 수 있습니다.
실패한 원 deck/log는 바꾸지 말고 새 attempt에서 실행합니다.

### 작성 범위

계획했던 변경은 D8 adapter·조건 편집·결과 읽기·사용 예제입니다. 실제 변경에 포함한 공통 접점은
기존 backend/catalog 등록, research_execution의 보존 source 해석, Post의 mask/identity를
물리 측정 대상으로 고르지 않게 하는 필터입니다. 기존 appearance의 한글 plot font 함수를
호출만 하며 스타일 framework를 추가하지 않았습니다.
CURRENT_STATE/.moai/installer/바로가기 파일은 수정하지 않습니다.


### SURF/SEG 고정폭 교정

Root의 0681d19 실행에서 기본 24검사와 Data→rainflow→Study→cold reopen은 통과했습니다.
실제 두 native 경로는 Starter ERROR78에서 멈췄으며 Engine 결과로 표시하지 않습니다.

실행본의 각 SURF/SEG 행은 명시 segment 번호와 N1/N2/N3/N4의 10자리 정수 다섯 개로 씁니다.
삼각면은 N4=N3, 사각면은 서로 다른 네 절점입니다. 먼저 변환기의 면 방향과 원 요소 면을
대조한 뒤 해당 데이터 행만 교체합니다. 다른 카드·필수 헤더와 원 converted deck은 보존합니다.
admission도 다섯 슬롯·존재하는 절점·중복 segment·삼각 반복 규칙을 직접 검사합니다.

근거는 pinned radioss110/SETS/surf.cfg의 5I10과 hm_read_surf.F의 N1~N4 읽기입니다.
**native reader는 N4=0도 N3로 해석합니다.** 따라서 원 ERROR78의 원인을 단순히
“삼각면은 네 번째 절점이 필수”라고 단정하지 않습니다. 명시 형식은 모호함을 제거하는
소스 교정이며 동일한 작은 실제 Starter 경로가 그 오류 해결을 확인해야 합니다.
작성자 native 실행은 NOT_RUN입니다.


### Starter의 빈 물리행 교정

Root는 2348bab에서 변경 12검사가 통과했으나 두 native 경로의 ERROR78이 그대로임을
확인했습니다. 이후 실패 deck 사본의 /END 앞 **추가 빈 개행 1바이트만 제거**하자
Starter가 exit0/오류0으로 끝났습니다. Engine은 실행하지 않았습니다. 진단 사본에
engine 입력을 복사하지 않아 발생한 warning1589는 별도이며 제품의 경고 거절 기준은 유지합니다.

원인은 무중력 rows=[]에서도 global_gravity가 빈 물리행을 삽입한 것입니다.
마지막 SURF/SEG의 그 행이 0 절점 segment로 읽혔습니다. 이제 추가할 중력 카드가
없으면 입력을 그대로 보존하고, 있을 때만 실제 카드 행을 기존 개행 형식으로 삽입합니다.
SURF admission은 주석과 빈 물리행을 구별하여 빈 행을 명시 거절합니다.
원 converted deck과 실패 결과는 변경하지 않습니다.

5I10/면 방향 검사는 유지하되, **원 ERROR78의 확인된 원인은 이 추가 빈 행**입니다.
회귀 검사는 LF/CRLF, 마지막 개행 유무, 중력 추가/제거와 빈 행 거절을 확인합니다.
이번 소스의 작성자 Python/native 실행은 NOT_RUN이며 진단 성공은 Root의 별도 실행입니다.
