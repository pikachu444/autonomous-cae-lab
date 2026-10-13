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
   C3D4, C3D8/R, C3D10, 등방 탄성/단조 소성, 밀도, 고정 병진 구속,
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
7. 결과에서 실제 에너지/질량 이력을 고르고 기존 **Post**로 등록된 native 장을 엽니다.
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

## 네 작업과 잔여

| 작업 | 이 체크포인트 코드 | 아직 남은 제품 기능/확인 |
|---|---|---|
| FN-16-01 초기조건·실행 | 사용자 FE import/native capture, 병진·spin·높이, TYPE24, 시간·질량 scaling, owned 실행 | native 실제 admission/readback, 자동 COM/관성 적분, 더 넓은 하중·열/속도 의존 법칙 |
| FN-16-02 결과 판단·연결 | 실제 global 에너지/질량 이력, raw/mask 포함 Post, 저장/재열기와 기존 Numerical 연결 | pair force/impulse의 개별 의미 선택, 부분 출력의 명시 후처리, balance/sensitivity 비교와 공학 판정 |
| FN-17-01 손상·재닫힘 | 기존 무손상 벌크/소성의 명시 범위, 원 결과 배열 보존 | LAW117/JC 명시 writer, cohesive mesh orientation/재닫힘 접촉, damage/opening/slip/part energy의 사용자 경로 구현 중 |
| FN-17-02 반복·수명 | 단조 결과를 수명으로 바꾸지 않음 | 실측/원응력 이력의 rainflow+보정 S-N/Miner와 UI 연결, cyclic constitutive/cohesive fatigue 후속 |

남은 항목은 문서만으로 완료 처리하지 않습니다. 실제 코드와 실행 근거를 이어서 추가합니다.

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
