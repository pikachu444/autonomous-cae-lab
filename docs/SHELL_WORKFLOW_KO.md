# 판재 셸 해석 사용법

FreeCAD에서 판재의 두께·방향·압력을 설정하고 CalculiX로 계산한 뒤 ParaView에서 변위와 응력을 확인합니다. 기존 Pre와 Post를 사용하며 WSL이나 별도 유료 프로그램은 필요하지 않습니다.

## 현재 사용할 수 있는 범위

S8 셸의 두께·방향·압력 편집, 입력 생성, 계산 실행, 상·하면 및 내부 결과 읽기와 저장·재열기를 연결했습니다. Windows의 FreeCAD 1.1.4와 CalculiX 2.22로 32개 S8 요소의 판재를 계산했고, ParaView에서 응력 성분 선택과 프로젝트 저장·재열기를 확인했습니다. 셸과 조립 운동을 함께 편집한 문서도 한 번의 저장으로 두 편집을 남기도록 연결했습니다.

상·하면 응력은 솔버가 절점으로 복원한 값입니다. 정확한 표면 적분점 응력은 아직 제공하지 않습니다. 내부 적분점 결과와 구분해 사용하세요. 아래 지원 범위를 벗어난 셸 해석은 이번 기능에 포함되지 않습니다.

셸 화면은 실제 FreeCAD에서 보통 크기와 좁은 크기로 확인했습니다. 전체 도킹·마우스 조작 과정이나 일반 모델의 공학적 적합성을 모두 검증했다는 뜻은 아닙니다. 최신 개발 상태는 [현재 상태](../CURRENT_STATE.md)에 있습니다.

## 첫 지원 범위

균질 등방 선형탄성, 3D, 선형 정적 한 단계, S8 전적분 셸만 허용한다. 한 active analysis의 native 메시 하나, 재료 하나, 단면 하나, 균일 압력 하나와 native Fixed 조건/명시 고정 절점을 사용한다. 해석에는 선택한 S8 요소만 참여한다. 선택 대상은 공개 예제 이름이나 치수로 분기하지 않는다.

압력은 선택 영역 전체에 작용한다. 고정 절점은 1–6 자유도를 고정하며 native Fixed 참조와 합친다. 서로 떨어진 참여 영역마다 명시 고정 절점이 있어야 한다. 이 검사는 강체 이동의 완전한 수학적/공학적 안정성 승인이 아니다. 결과를 설계 승인에 쓰기 전 사용자가 경계조건과 메시 수렴을 별도 검증해야 한다.

S8R, 막(M3D8 등), 삼각형, 혼합 solid/shell, 다중 단면/재료, 적층, 비선형·소성·접촉, 시간 의존 하중, thermal, 사용자 `*NORMAL`, 사용자 MPC/변위 조건은 이번 profile에서 허용하지 않는다. 다른 profile의 reader에 S8을 추가하지 않았다. 활성 미지원 객체는 해당 객체를 표시해 차단한다. 조립 Placement가 적용된 mesh 객체는 native 전역 좌표에 배치가 반영된 메시로 바꾸어야 한다. 첫 profile은 mesh 및 상위 객체의 global Placement가 identity인 메시만 받는다. CAD 자체의 배치는 참조 검사에서 별도로 보존한다.

## Windows에서 시작

기존 Lab 서비스/설치 설정과 `CAELAB_FREECAD_EXE`, `CAELAB_PARAVIEW_EXE`, 기존 Python을 그대로 사용한다. `ccx.exe` 2.22가 **기존 서비스 프로세스의 PATH**에 있어야 한다. 모델 인자로 임의 실행 경로나 커맨드를 받지 않는다. 서비스용 기존 내부 연결은 유지하지만 제품 화면은 FreeCAD/ParaView/Qt이며, 브라우저 UI나 새 서버를 추가하지 않는다.

기존 데스크톱의 **Pre 열기**로 FreeCAD를 연다. 기존에 설정한 서비스 주소가 환경에 있다면 다음 기존 진입도 사용할 수 있다.

```powershell
python -m apps.research.desktop --service $env:CAELAB_SERVICE_URL pre
```

환경값이 없는 상태에서 새 주소를 임의로 만들어 실행하지 않는다. 현재 설치의 실행 단축키/설정에 있는 주소를 사용한다. WSL이 필요하지 않다.

FreeCAD 메뉴 **매크로 → 매크로…**에서 `examples/shell/OpenPlate.FCMacro`를 실행한다. 저장소 루트와 새 `.FCStd` 경로를 선택한다. 기존 파일은 덮어쓰지 않는다. 이 macro는 파라메트릭 `Part::Plane`, 공유 중간절점을 가진 native S8 메시, native Analysis/CalculiX/material/2D section/pressure/Fixed를 생성한다. 분석용 가짜 결과는 만들지 않는다. 길이·폭·분할을 바꿔 만들려면 native Python console에서 다음을 실행한다.

```python
from examples.shell.generate_plate import create
create(r'C:\CAE\shell_cases\plate_120x50.FCStd', length=120., width=50., nx=6, ny=3)
```

예제의 Plane 길이/폭은 native 속성으로 편집할 수 있다. 기존 메시가 자동으로 새 형상을 따라가는 것은 아니다. 형상을 바꾸면 native에서 메시를 재생성/교체하고 아래의 대상 복구를 해야 한다. 기존 사용자의 S8 mesh/면 기반 모델도 동일한 경로로 시작한다. 별도 형상 이름/치수 검출 분기는 없다.

## 편집 → 입력 검토 → 계산

1. native 트리에서 작업할 FEM 해석을 활성화한다. **판재 → 판재 셸…**을 연다. 해당 해석·메시·CalculiX 솔버를 선택해 **선택 모델로 시작**한다. 기존에 저장된 초안을 열면 초기값으로 덮어쓰지 않는다.
2. native 3D에서 면을 선택하고 **선택 면 확인 → 대상 적용**을 누른다. 또는 **요소 선택…**에서 메시와 참여 S8 요소를 표로 선택한다. native 메시 객체 전체 선택도 가능하다. 미리보기는 실제 선택/강조만 바꾸며 취소하면 기존 초안과 적용 상태가 유지된다.
3. 두께 `2`, offset `0`, 탄성계수 `210000 MPa`, 포아송비 `0.3`, 압력 `0.001 MPa`를 입력한다. 압력과 재료 값은 예시이며 사용자의 실제 값을 입력한다. native Fixed 조건 또는 **고정 절점…**을 확인한다. 한 점만 임의로 고정해 계산 통과를 만들지 않는다.
4. **두께·방향 보기**에서 요소 법선과 국부 1축, 상·하면 위치를 본다. 처음 미확정 법선은 미리보기용 native 방향일 뿐이다. **메시 법선 확인**으로 명시 확정하고 **속성 적용**을 누른다. 국부 1축이 법선과 평행하거나 요소가 접히면 해당 행/요소에서 차단한다.
5. **초안 저장** 또는 기존 프로젝트 저장으로 `.caepre`를 저장한다. `0`, `1e`, 빈 숫자는 빨간 오류행에서 고칠 수 있고 저장할 수 있다. 유효하지 않은 초안에서는 속성 적용/입력 준비/실행을 하지 않는다. 저장과 적용은 별개다.
6. **입력 준비**를 누른다. FreeCAD native writer가 만든 mesh/단면/압력/재료 조각을 검증하고 별도 동결 폴더에 쓴다. 이 단계는 CalculiX를 실행하지 않는다. 읽기 전용 입력창에서 `*ELEMENT, TYPE=S8`, `*SHELL SECTION`, `OFFSET`, 다음 행의 실제 두께 `2`를 확인한다.
7. **계산 실행**으로 방금 준비한 입력으로 계산한다. 입력 준비 뒤 편집하거나 native에서 객체를 바꾸면 새 입력 준비를 요구한다. 같은 계산을 다시 확인하면 기존 작업을 연다. 다시 계산하려면 새 입력을 준비한다. 중단은 기존 계산 목록에서 한다.
8. 완료 후 **결과 열기** 또는 기존 계산 목록 → Post로 연다. 다음 절의 위치/채널 이름을 사용한다. 두께를 `3`으로 바꿀 때는 속성 적용 → 새 입력 준비 → 실제 카드 `3` 확인 → 실행을 반복한다. 기존 2 mm 입력과 결과는 남는다.

메뉴·도크가 좁으면 속성 표의 가로 스크롤과 도크의 세로 스크롤을 사용한다. 원래 native Qt 글꼴을 상속하며 별도 웹 폰트나 브라우저를 쓰지 않는다. Windows에서 한글과 오류행을 확인했다. 잘못된 숫자는 입력한 그대로 남으며 해당 행에 수정할 이유가 표시된다.

## 방향과 offset의 계약

원 native S8 순서를 반전할 때 `(1,4,3,2,8,7,6,5)`로 바꾼다. shell 기준면 좌표는 그대로다. 양의 법선을 `n`, 두께를 `t`, offset/두께 비를 `o`라고 하면 native 전개의 위치는 다음과 같다.

```
bottom = reference - t*(0.5 + o)*n
top    = reference + t*(0.5 - o)*n
```

**법선 반전**은 `n → -n`과 `o → -o`를 함께 적용하므로 기존 물리적 상·하면 위치를 유지하면서 이름이 서로 교환된다. **공간상 압력 방향 유지**를 선택하면 압력 부호도 바꾼다. 해제하면 압력의 법선 상대 부호가 유지되어 물리적 작용 방향이 바뀐다. 임의로 orientation 문자열만 수정해서 이 규칙을 우회할 수 없다.

이 패널의 양의 압력은 양의 법선 반대 방향이다. FreeCAD native whole-shell pressure writer의 `P` 카드 부호를 그대로 사용한다. `P1/P2…` solid face pressure로 해석하지 않는다. 요소별 `*ORIENTATION`은 사용자가 고른 전역 방향을 요소 중심 접평면에 투영한 축을 사용한다. 결과의 `_surface_local`도 그 **동일한 요소 중심 고정 축으로의 정확한 기저 변환**이다. 휜 요소 각 적분점의 native 재료 축이라고 부르지 않는다.

## 결과 위치와 복원 수준

| 저장 채널 | 실제 위치와 의미 | 파일 |
|---|---|---|
| `U_mm`, `U_magnitude_mm` | native 확장된 상·하면 절점의 변위, mm | `surface_*.vtu`, 원 FRD |
| `S_surface_recovered` | 그 확장 절점의 native 외삽/평균 응력, MPa. 정확한 표면 적분점 응력이 아님 | `surface_*.vtu`, 원 FRD |
| `E_surface_recovered` | 그 확장 절점의 native 복원 total strain. 전단은 tensor 성분이며 engineering gamma가 아님 | `surface_*.vtu`, 원 FRD |
| `S_surface_local`, `E_surface_local` | 같은 관측값을 저장된 요소 중심 사용자 축으로 변환 | `surface_*.vtu` |
| `S_internal`, `E_internal` | S8의 27개 **내부** 적분점 관측, 가공된 표면 값이 아님 | `internal_*.vtu`, 원 DAT |
| `ShellSide`, native/shell/element IDs, normal | 상면 `+1`, 하면 `-1`, 원 S8/확장 절점 대응 | 상·하면 VTU와 JSON |

FRD tensor 성분은 `XX, YY, ZZ, XY, YZ, ZX`이다. DAT의 `XX, YY, ZZ, XY, XZ, YZ`를 명시적으로 이 순서로 정렬한다. 원 DAT token과 원 순서도 보존한다. ParaView의 6성분 magnitude를 von Mises 응력이라고 사용하지 않는다.

상·하면 식별의 1차 근거는 native `shell.12d`다. 원 S8 절점 8개와 같은 요소 번호의 확장 `C3D20 L` 절점 20개를 직접 읽는다. 연결 순서의 bottom은 1–4/9–12, top은 5–8/13–16, 두께 중간은 17–20이다. FRD HEX20 배열 순서의 중간절점 배치를 별도로 대조한다. 원 요소 번호·원 절점·확장 절점·side·원자료 행·복원 방식을 저장한다. 좌표가 가까운 절점을 골라 대응하지 않는다.

FRD 실제 확장 좌표로 두께와 offset 기준면을 다시 확인한다. 허용 오차는 native float32/E12.5 출력 양자화 범위와 부동소수 연산 범위이며 임의 공학 허용 오차가 아니다. 전개 위치를 구분할 수 없거나 `.12d`가 없거나 형식/연결성이 다르면 결과를 차단하고 원파일은 남긴다. native 포맷을 모르는 상태에서 평균 값을 적분점으로 바꾸어 붙이지 않는다.

DAT `COORD`가 완전하게 존재하는 증분만 내부점 cloud를 만든다. `COORD`가 없는 점 위치를 형상으로 계산해 채워 넣지 않는다. 27점의 두께 자연좌표는 `-0.774596669241483, 0, +0.774596669241483`이며 표면 `±1`과 다르다. 내부점으로부터 표면 응력을 임의 외삽하지 않는다.

ParaView에서는 `ShellSide`로 Threshold를 두 개 만들어 `+1`/`-1`을 분리한다. 두 Threshold를 나란히 보면서 `U_mm`의 실제 성분 또는 `S_surface_recovered`, `E_surface_recovered`의 `XX` 등을 선택한다. `NativeElementId`와 `ShellNodeId`를 함께 조회해야 공유 절점의 어느 요소/side를 읽는지 구분된다. Lab의 writer는 요소/side별 표시 절점을 분리하지만, **CalculiX가 이미 수행한 native 평균화를 되돌리지는 않는다.** 응력 불연속면의 비평균 요소측 표면 결과는 이 경로의 제공 채널이 아니다.

## 저장과 솔버 없는 재열기

입력 동결 폴더는 `snapshot.json`, `editable.FCStd`, `native_mesh.inp`, `mesh.json`, `shell.inp`, 가능한 경우 `editable.caepre`를 보존한다. 원 설계를 덮어쓰지 않는다. 계산 폴더의 `retained_inputs/`도 해당 입력을 보존한다.

결과의 `post/` 폴더 전체를 복사한다. `shell_inspection.json`, `shell_values.json`, 모든 `surface_*.vtu`, `internal_*.vtu`, `surfaces.pvd`, `source/`의 원 `inp/12d/frd/dat`와 로그를 함께 유지한다. VTU 한 개만 복사한 것은 표시용 복사이지 전체 원자료 보존이 아니다.

기존 Post는 저장된 VTU/PVD를 ParaView native로 열 수 있다. Lab의 승인된 로컬 입력 폴더에서 `shell_inspection.json`을 선택하면 위치/원자료 정보를 함께 등록한다. Python으로는 다음 검사/조회가 가능하다. 이것은 FreeCAD나 ccx를 import/실행하지 않는다.

```powershell
python -m examples.shell.check_saved_result C:\CAE\saved_shell\shell_inspection.json
python -m examples.shell.check_saved_result C:\CAE\saved_shell\shell_inspection.json --element 1 --node 1
```

번호를 생략하면 저장된 실제 첫 요소/절점을 선택한다. 출력은 선택 위치와 그 위치에 실제 존재하는 채널뿐이다. 재열기는 원자료 hash뿐 아니라 `.12d`/FRD/DAT에서 재읽은 관측값 및 생성 VTU/PVD 바이트까지 대조한다. 솔버는 호출하지 않는다. native ParaView의 자체 렌더링 보간과 이 reader가 제공하는 원 관측 채널은 구분한다.

## 참조 상실, 실패, 취소

면·메시·고정 참조 형상이나 배치가 달라지면 입력 준비를 막고 해당 객체/요소 위치를 표시한다. 초안 저장은 계속 가능하다. **요소 선택…**에서 새 메시와 요소를 미리 보고 **대상 적용**으로 명시 복구한 뒤 법선을 다시 확인한다. CAD는 변했는데 mesh hash가 동일하면 native 메시 재생성을 먼저 요구한다. 새 선택 미리보기를 취소하면 기존 초안과 적용 상태는 유지한다.

native 재료/단면/압력/솔버를 삭제·교체했으면 **대상 연결 복구…**에서 현재 해석의 객체를 명시 선택한다. 재료·단면·압력을 새로 만들도록 선택해도 실제 생성은 다음 **속성 적용** 때만 한다. 활성 재료가 바뀌었는데 예전 적용 상태로 조용히 계산하는 경로는 허용하지 않는다. 해석 객체 자체를 삭제한 초안도 저장/읽기는 남지만, 다른 Analysis로의 일괄 이전 UI는 첫 지원 범위가 아니다. native에서 해석을 되살리거나 새 해석에서 새 셸 초안을 작성한다.

입력 작성 실패는 그 시도의 파일과 `preparation_failure.json`을 남기고 완료 manifest를 공개하지 않는다. 계산 취소/실패는 기존 소유 프로세스 정리 이후 원파일을 보존한다. 잘린 필드는 완성된 다른 증분에서 가져오거나 0으로 채우지 않는다. 같은 증분에서 끝까지 읽은 필드만 부분 결과로 보관한다. 프로세스 정리 실패는 성공 또는 안전한 종료로 봉인하지 않는다. 실패/부분 결과를 전해석 성공으로 바꾸지 않는다.

## Windows 실제 확인 절차

별도 `examples/shell/WINDOWS_CHECKLIST.md`를 따른다. `CheckPrepared.FCMacro`는 실제 FreeCAD host에서 이미 준비된 입력을 읽는 보조 검사다. 이 macro를 실행했다고 native writer/solver가 실행된 것으로 계산하지 않는다. native writer 실행 확인은 앞서 입력 준비를 실제 수행한 기록으로 한다.

## 개발 참고

원 native 계약은 다음 공개 소스를 고정해 확인했다.

- FreeCAD/FreeCAD `1.1.4`: `src/Mod/Fem/femsolver/calculix/write_femelement_geometry.py`, `write_constraint_pressure.py`, `write_femelement_material.py`, `write_mesh.py`, `write_step_output.py`; `src/Mod/Fem/App/FemMesh.cpp`.
- Dhondtguido/CalculiX `cff1bb12ec7d24ad9048a1f54ae243a18d1a0b54` (2.22): `src/gen3delem.f`, `src/gen3dfrom2d.f`, `src/frdvector.c`, `src/elfiles.f`, `src/orientations.f`, `src/printout.f`, `src/gauss.f`.

FreeCAD의 전체 writer Task/solver 실행을 우회 복제하지 않고, 실제 mesh exporter와 section/material/pressure writer를 호출한 뒤 이 첫 profile에서 허용되는 의미인지 검사한다. 해석 step/출력/선택 set의 작은 compiler는 셸 전용이다. 기존 C3D10 동결/접촉 reader의 family 검사를 풀면 잘못된 결과 위치를 정상으로 통과시키므로 채택하지 않았다. FRD 2D 평균면 출력이나 좌표 근접 매칭도 상·하면 손실 때문에 채택하지 않았다. 새 viewer나 scheduler 대신 기존 native Post와 JobManager를 사용했다.
