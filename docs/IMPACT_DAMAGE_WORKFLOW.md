# 사용자 FE 충격·손상 연구

## 현재 인도 범위

2026-10-14 main에 사용자 FE 입력, 충격 조건 편집, 응집 손상과 반복하중 평가를
통합했습니다. Windows에서 공개 응집 시편을 실제 계산하고 ParaView로 결과를 열어
21개 시각을 확인했습니다. 계산 문서와 후처리 프로젝트의 저장·재열기도 확인했습니다.
실제 결과 화면은 [한글 사용 안내](USER_GUIDE_KO.md#유한요소-모델에-충격-조건-넣기)에 있습니다.

Pro 작성 환경에서 실행하지 못했던 항목은 Codex의 Windows 확인과 구별해 기록했습니다.
위 확인은 공개 예제의 실행 범위입니다. 일반 CAD에서 시작하는 모든 충돌·파괴 해석이나
FN16/17 전체 완료를 뜻하지 않습니다. 예제의 계면 손상값은 0이며 재료 시험값에 맞춘
모델이 아닙니다. 앞선 단일 사면체 예제의 에너지 발산도 해결된 것으로 처리하지 않습니다.

기존 고정 explicit.openradioss 모델과 원 검사 기준은 유지합니다.
새 explicit.opencourant.model은 사용자가 선택한 FE 입력 묶음을 기존 Simulation 문서,
JobManager, 결과 보존, Numerical의 선언 입력 바인딩으로 실행합니다.

## 사용자 작업

1. 독립 해석 창에서 **새 해석 모델 → 사용자 FE 충격 (OpenCourant)** 를 선택합니다.
2. **연구 → 충격 조건… → 유한요소 파일 열기…** 에서 주 INP와 **입력 제출 작업 폴더**를 고릅니다.
   단위 Mg/mm/s/N/MPa를 직접 확인합니다. 가져오기는 계산을 실행하지 않습니다.
   C3D4, C3D8/R, C3D10 및 명시 COH3D8, 등방 탄성/단조 소성, 밀도, 고정 병진 구속,
   정확한 요소 면 집합을 지원합니다. 상대 INCLUDE는 아래 입력 묶음 경로로 보존합니다. 미지원 카드·온도 의존·이방성은 거절하며
   원 파일을 수정하지 않습니다.
3. 원 절점 집합이 없으면 **모델과 집합**에서 요소 집합을 골라 **운동 대상 만들기…**를 사용합니다.
   **초기 운동**에서 그 절점 집합을 추가해 병진 속도, 각속도, 회전 중심과 초기 위치를 입력합니다.
   각속도는 rad/s이며 초기 절점 속도 v+ω×r로 반영합니다.
   '높이에서 놓기'는 병진 속도 0에서 중력 반대 방향으로 시작 위치를 옮깁니다.
   비영 속도가 있으면 방식 전환 시 0으로 바꿀지 직접 확인하며 취소하면 원 속도와 방식을 보존합니다.
   '높이를 충돌 속도로 환산'은 시작 위치를 옮기지 않고 sqrt(2gh)를 적용합니다.
   두 경우 중력 방향·크기가 필수입니다. 높이와 속도를 몰래 중복하지 않습니다.
4. 원 접촉면이 없으면 **모델과 집합 → 접촉면 만들기…**에서 형상을 확인하며 면을 선택합니다.
   **접촉**에서 면 A/B와 TYPE24, 마찰계수를 명시합니다.
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

개발자가 관련 동작을 확인할 때 쓰는 명령입니다. 원 작성자의 실행은 NOT_RUN이었으며,
후속 Windows 실행·교정 결과는 [현재 상태](../CURRENT_STATE.md)에 기록했습니다.
사용자가 예제를 여는 데 아래 검사를 먼저 실행할 필요는 없습니다.

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

## 여러 파일의 사용자 메시 가져오기와 대상 만들기

이 후속 기능은 원 INP에 운동용 NSET나 접촉 SURFACE가 없는 사용자 솔리드 메시에도 적용합니다.
특정 예제 모양을 판별하거나 예제의 번호를 제품에 고정하지 않습니다. 지원 카드·요소·단위는
기존 실행 계약을 따릅니다. 가져오기, 대상 편집, 입력 확인, 저장은 솔버를 실행하지 않습니다.

### 파일을 가져오고 확인하기

1. **유한요소 파일 열기…**에서 주 파일과 그 해석을 제출할 **입력 제출 작업 폴더**를 선택합니다.
   예를 들어 `model.inp`와 `Mesh Parts/`가 함께 있는 폴더입니다. 모든 중첩 INCLUDE는
   이 한 폴더를 기준으로 읽습니다. 포함 파일이 들어 있는 하위 폴더로 기준을 바꾸지 않습니다.
2. 원 입력의 **Mg, mm, s, N, MPa** 단위를 직접 확인하고 **입력 확인**을 누릅니다.
   따옴표로 둘러싼 공백 파일명, Windows 역슬래시, 대소문자 없는 키워드, 키워드 이어쓰기,
   중첩·반복 INCLUDE를 처리합니다. 파일명의 대소문자는 보존합니다. 서로 대소문자만 다른
   두 경로는 Windows에서 구별할 수 없어 거절합니다.
3. 파일 선택 목록에서 실제 원문을 읽고 **가져오기**를 누릅니다. 미지원 카드가 있으면
   원파일·행을 알려 주고 **초안으로 가져오기**가 가능합니다. 잘못된 초안은 저장할 수 있으나
   계산 입력 생성과 실행은 차단합니다. 누락 파일·순환·폴더 밖 경로·읽기 중 파일 교체는
   가져오기를 끝내지 않습니다. 취소하거나 실패하면 열어 둔 조건을 바꾸지 않습니다.
4. 기존 입력을 교체할 때만 기존 대상·운동·접촉·선택 응답을 비울지 확인합니다.
   단순 집합 생성·편집은 현재 숫자 입력과 `1e` 같은 미완성 초안을 다시 채우지 않습니다.

원파일 bytes와 상대 경로, 반복 포함 순서, 펼친 입력, 원행 대응을 같은 Simulation 초안에
보존합니다. 원파일을 옮긴 뒤에도 저장 문서를 다시 열 수 있도록 외부 경로에 의존하지 않습니다.
새 실행은 기존 attempt 안에 `source_bundle/files/`의 정확한 원파일,
`source_bundle/manifest.json`, `flattened.inp`, 별도 `generated_sets.json`을 보존합니다.
기존 `original.inp`는 호환을 위해 **펼친 입력**이며 주 파일의 원 bytes는
`source_bundle/files/<주 파일 상대 경로>`입니다. 변환기와 실제 실행 deck도 기존대로 남습니다.

### 운동 대상과 접촉면

**모델과 집합**의 요소 집합을 선택하면 전체 형상에서 해당 절점, 요소 수와 XYZ 범위를
확인할 수 있습니다. 입체/XY/XZ/YZ 보기를 바꿀 수 있습니다. 요소 집합은 부품이라는
가정을 하지 않으며, 겹친 집합·공유 절점은 그대로 유지합니다.

- **운동 대상 만들기…**는 선택 요소의 모든 연결 절점을 합친 명시 NSET를 만듭니다.
  C3D10 중간 절점도 포함합니다. 이름과 원 요소 집합을 확인하고 만든 뒤 **초기 운동**에서
  선택합니다. 병진 속도·각속도·중심·초기 위치와 높이 모드의 기존 의미를 유지합니다.
  서로 겹친 운동 대상의 충돌 검사는 실행 전에 계속 적용됩니다.
- **접촉면 만들기…**의 **전체 메시의 외곽면**은 선택 집합만 따로 떼어 검사하지 않습니다.
  다른 요소와 공유하는 면은 제외합니다. 표의 행과 형상 면을 클릭해 선택하고 이름을 정합니다.
  전체 외곽면을 자동으로 접촉쌍에 넣지 않습니다.
- 필요한 경우 **요소 면 직접 선택**에서 내부면을 고를 수 있습니다. 선택한 내부면 개수를
  확인하고 사용 여부를 명시해야 합니다. 원 메시의 면 방향을 뒤집어 고치지 않습니다.
  C3D10의 공유 면 동일성은 6개 절점과 모서리별 중간 절점으로 판정합니다. 실제 TYPE24는
  3개 모서리 꼭짓점의 평면 삼각형을 사용하며 곡면 접촉이 아닙니다. COH3D8 생성 면은
  물리적인 양쪽 S1/S2만 허용합니다.
- **집합 수정…**에서는 생성한 대상의 원 요소 집합 또는 면 선택을 바꿉니다. 같은 이름을
  사용하는 조건이 대화창에 표시됩니다. **변경 반영** 전에는 조건이나 집합이 바뀌지 않습니다.
  **집합 삭제**는 참조 중이면 해당 조건을 알려 주고 차단합니다. 먼저 조건 대상을 바꾸거나
  조건을 삭제해야 합니다. 원파일의 집합은 원문을 그대로 보존합니다.

미리보기는 모서리 면으로 표시하며 많은 메시에서는 표시 수를 제한했다는 문구를 남깁니다.
이 표시 제한은 실제 집합과 계산 입력의 절점·면을 삭제하지 않습니다. 비다양체, 반대 방향이
아닌 내부 공유 면, 뒤집힌 모서리 면, 불일치한 C3D10 중간 절점은 생성 전에 거절합니다.
이는 전체 곡면 요소의 Jacobian/메시 품질을 검증했다는 뜻이 아닙니다.

### 입력 파일만 생성하거나 명시 계산하기

**모델과 집합 → 입력 확인 → 변환용 INP 저장…**은 현재 대상과 운동 조건을 합성한 INP를 새 파일로
저장합니다. 확인 창을 연 시점의 입력을 사용하고 기존 파일을 덮어쓰지 않습니다.
계산은 제출하지 않습니다. 실행하려면 **편집 반영 → 적용 → 저장 → 계산**을 사용합니다.
기존 Starter/Engine, 에너지·힘·선택 이력, Post 등록, 실패·취소 기록을 재사용합니다.
원 bundle과 생성 집합은 별개이므로 입력 확인에서 합성한 NSET/SURFACE를 직접 대조할 수 있습니다.

내보낸 INP는 변환기에 넘길 입력입니다. 응집 손상 법칙, 솔버의 출력 주기와 질량
스케일링 등 모든 해석 설정을 담은 OpenCourant 실행 묶음은 아닙니다. 전체 조건은
해석 문서를 **저장**하여 보관하고, 앱의 **모델 평가**로 실행합니다.

### 공개 다부품 입력으로 따라 하기

저장소 `examples/impact/include-project/model.inp`를 주 파일로, 그 폴더를 제출 폴더로
고릅니다. 두 C3D8 솔리드와 중첩 포함 파일, 공백 경로를 담은 공개 합성 예제입니다.
원 입력에는 `BASE`, `MOVING` 요소 집합과 하부 지지 절점만 있으며 운동/접촉 대상은 없습니다.

1. `MOVING`에서 운동 대상 `MOVEMENT`를 만듭니다.
2. `BASE`의 S2를 `LOWER_CONTACT`, `MOVING`의 S1을 `UPPER_CONTACT`로 만듭니다.
3. `MOVEMENT`의 병진 Z 속도를 −10 mm/s, 각속도를 0으로 지정합니다.
4. 접촉 A=`UPPER_CONTACT`, B=`LOWER_CONTACT`, TYPE24, 마찰 0을 명시합니다.
5. 종료 시간을 0.004 s로 정해 입력을 확인합니다. 초기 간격은 0.02 mm이고, 모든 값은
   연결 확인용 합성 조건입니다. 재료 보정·수치 정답·공학 승인을 뜻하지 않습니다.

동일 입력을 기존 서비스에 저장하거나 입력 파일만 만들 수 있습니다.

```powershell
python -m examples.impact.include_project --export .\include-impact.inp
python -m examples.impact.include_project --service http://127.0.0.1:18767
Start-CAE-Lab.cmd -Tool simulation -DocumentId <출력된 문서> -Port 18767 -Store <같은 저장소>
```

`--run`을 추가하거나 창에서 **계산**을 눌렀을 때만 실제 계산합니다. 실행 환경은 위의
기존 OpenCourant Windows runtime이며 WSL이나 새 라이브러리가 필요하지 않습니다.

관련 최소 확인:

```powershell
python -m pytest tests/test_impact_project.py tests/test_impact_project_ui.py -q
# 설치된 OpenCourant에서 이 새 입력 한 건만 명시 실행:
$env:CAELAB_RUN_IMPACT_PROJECT='1'
python -m pytest tests/test_impact_project.py -k installed_include_model -q -s
```


명시 native 검사는 출력에 표시하는 `cae-impact-project-` 임시 폴더를 성공·실패 모두 남깁니다.
통합 확인 뒤 필요한 원입력·변환 deck·로그·Post를 별도로 보존한 다음 운영자가 정리합니다.

작성 환경에서는 bundle/위상/실제 pinned INP2RAD와 적용 물리 카드, 실제 offscreen Qt
선택·취소·초안 보존을 실행했습니다. HTTP owner 저장·cold reopen은 기존 `filelock` /
`jsonschema` 의존성이 없는 작성 환경에서 **NOT_RUN**입니다. 해당 검사는 정상 설치 환경에서
실제 HTTP와 새 Workbench로 실행하도록 포함했습니다. Windows Starter/Engine/Post도
**NOT_RUN**이며 opt-in 검사를 제공합니다. 로컬 Qt에는 한글 글꼴이 없어 한글 렌더 수용은
Windows에서 별도로 확인해야 합니다. 화면의 모델과 면 선택은 실제 예제 연결 정보를 사용했습니다.
마지막 면 선택 복원·큰 메시 선택면 표시 교정 뒤에는 작성 executor가 연결 해제되어 추가 Qt 재실행은
**NOT_RUN**입니다. 해당 두 회귀는 제출 검사에 포함하며, 앞선 실행 통과와 구별합니다.

### 구현 경계와 남은 범위

- 공식 [Abaqus 입력 문법](https://docs.software.vt.edu/abaqusv2025/English/SIMACAEMODRefMap/simamod-c-inputsyntax.htm)의
  제출 디렉터리 기준을 사용합니다. pinned INP2RAD의 직접 INCLUDE 기능은 중첩/따옴표/플랫폼
  경로 계약을 완결하지 않으므로, 작은 import helper가 보존 bundle을 펼치고 기존 strict parser와
  canonical writer에 넘깁니다. 변환기 자체를 다른 파서로 갈아엎지 않았습니다.
- 최대 128개 고유 파일, 24단계 포함, 1,024회 포함, 원/펼친 각 6 MiB 및 저장 source JSON
  6 MiB 한도를 적용합니다. 원문을 함께 보존하므로 실제 입력 허용량은 JSON 한도에 먼저 닿을 수
  있습니다. 생성 집합은 256개 이내입니다. 대형 프로젝트의 streaming/별도 자산 분리는 후속입니다.
- 공통 변경은 기존 문서 열기·명령 HTTP 두 경로의 본문 한도를 기존 문서 8 MiB와 작은 envelope에
  맞춘 것뿐입니다. 일반 요청의 128 KiB, 인증, 경로·문서 소유권 검사와 실행 권한은 유지합니다.
  `SimulationWindow`는 생성 집합을 기존 충격 편집기로 연결하고 보존 모델로 미리보기를 읽습니다.
- PART/INSTANCE의 지역 번호, native RAD 직접 편집/가져오기, shell/beam, 일반 재료/파괴 법칙,
  기존 미지원 시간변화 조건은 여전히 미지원입니다. 해당 카드를 원파일·행과 함께 거절하고
  원문을 보존합니다. 요소 집합을 부품으로 재해석하거나 동명 지역 번호를 합치지 않습니다.
- 보정·에너지 안정성·실제 접촉 동작과 공학 수용은 별도입니다. 이번 결과는 사용자 파일에서
  대상을 만들고 기존 실행/결과 소유자로 이어지는 제품 기능이며 전체 FN16/17 완료가 아닙니다.

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
| FN-17-02 반복·수명 | 정확한 보존 단축 응력 → 실제 MIT rainflow → 시험 범위별 S–N/Miner, 선택 곡선/사이클, 저장/Study/재열기 | native 응력 선택의 실제 연결 확인, 다축·일반 ε–N/평균응력 보정, 사이클 의존 소성/응집 피로의 실제 연성 |

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


### 기존 native 응력과 설치 패키지

반복하중 읽기는 Data 선언 외에 기존 MFront 탄성/Maxwell의 보존 물리 응력 성분,
Code_Aster J2의 정확한 Gauss 위치 SIXX/SIYY/SIZZ 선언도 해석합니다.
원 measure/coordinate_frame/성분명과 정확한 결과 참조는 바꾸지 않습니다.
계산 기록에 사용한 의미 대응만 별도로 남기며, 평균 응력장·PK1·전단·미지원 기준계를
단축 응력으로 재표기하지 않습니다. sensor/world 정렬은 계속 미확인입니다.

rainflow 원 구현은 설치되는 caelab._vendor 패키지로 옮기고 MIT 원문·NOTICE도
package-data에 포함했습니다. 원 함수 소스는 변경하지 않았습니다. pyproject의 이 데이터
포함 항목만 공통 설치 계약의 변경이며 새 의존성이나 자동 설치는 없습니다.
이 설치 패키지 및 native 메타데이터 검사는 작성자 실행 NOT_RUN입니다.


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


### Engine 종료와 저장 표본 범위

Root의 4a3d9b8 실행에서 Starter 0오류/0경고와 Engine NORMAL TERMINATION이
두 모델 모두 확인됐습니다. 기존 읽기는 마지막 TH 표본과 요청 종료 시각을 같다고
가정해 Post 앞에서 막혔습니다. 보존 자료의 별도 읽기에서는 user 10개 ANIM,
cohesive 21개 ANIM과 응답 4개/PVD 생성까지 확인됐습니다. 이 결과는 수치 정답이나
공학 수용이 아닙니다.

공식 pinned HIST2는 실제 증분 시각 TT에서 저장 조건을 검사합니다. 저장 후 시간이
진행되고 종료 조건을 검사하며, 마지막 추가 ANIM 증분에서는 TH를 생략합니다.
따라서 TH 끝값을 종료 시각으로 옮기거나, 마지막 간격을 임의 허용치로 확대하지 않습니다.
- Engine NORMAL TERMINATION/총 증분 수와 USER BREAK·비정상 종료를 별도로 읽습니다.
  USER BREAK도 exit0/정상 종료 문구를 남길 수 있어 성공 경로로 통과시키지 않습니다.
- 로그 FINAL TIME은 요청값입니다. 이를 실제 달성 시각이라고 저장하지 않습니다.
  실제 끝점이 입증되지 않으면 achieved_end_s와 달성 여부는 미정으로 남습니다.
- TH와 ANIM의 첫/마지막 시각, 개수, 요청 간격, 끝점 전 미관측 구간을 각각 기록합니다.
  final은 마지막 보존 표본이며, extrema/표본 적분도 보존된 범위만 의미합니다.
- TH binary record의 길이·끝 표식과 CSV 행/시간을 대조합니다. 잘린 record나 변환 중
  행 유실은 오류이며, variable timestep 전체의 미저장 증분 개수는 추정하지 않습니다.
  CSV 시간 비교는 공식 변환기의 binary32→%e 표현을 사용하며 공학 허용치를 추가하지 않습니다.
- 음의 내부 에너지와 비유한 값은 원 부호/토큰/quality로 남습니다. 음수/무효 행의
  위치만 진단에 표시하고, 정상 종료를 물리 유효 판정으로 바꾸지 않습니다.

공식 근거:
[HIST2 저장 시각](https://github.com/OpenCourant/OpenCourant/blob/cb760c206e346eff12161a2268b134ef9d48a4ef/engine/source/output/th/hist2.F),
[마지막 ANIM과 TH 분리](https://github.com/OpenCourant/OpenCourant/blob/cb760c206e346eff12161a2268b134ef9d48a4ef/engine/source/output/sortie_main.F),
[USER BREAK 종료](https://github.com/OpenCourant/OpenCourant/blob/cb760c206e346eff12161a2268b134ef9d48a4ef/engine/source/system/arret.F),
[HIST1 record 정의](https://github.com/OpenCourant/OpenCourant/blob/cb760c206e346eff12161a2268b134ef9d48a4ef/engine/source/output/th/hist1.F),
[기존 CSV 변환기](https://github.com/OpenCourant/Tools/blob/beaf8a17c880242bb7ad43325a20bd589dc0f533/output_converters/th_to_csv/src/th_to_csv.c).

보존 계산을 **solver/변환기 실행이나 파일 변경 없이** 확인:

    python -m examples.impact.inspect_retained --calculation <보존 calculation 폴더>

이미 별도 폴더에서 변환한 CSV를 쓰려면 --history-csv <그 CSV>를 추가합니다.
출력은 새 시간값이나 성공 결과를 생성하지 않는 읽기 진단입니다.

    python -m pytest tests/test_impact_timing.py -q

포함된 adapter 검사는 실제 pinned INP 변환기를 쓰되 Starter/Engine/ANIM은 명시 대역입니다.
작성자 Python/native 실행은 NOT_RUN입니다. 새 solver 캠페인 없이 기존 원본을 보존하여
읽기 경로를 확인할 수 있습니다.
