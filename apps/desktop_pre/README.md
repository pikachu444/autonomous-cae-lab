# CAD·유한요소 전처리

FreeCAD의 모델링·조립·메시 기능을 사용하고, CAE Lab의 치수 편집·운동·해석 조건·저장 명령을 같은 문서에 연결한다. 지원 범위와 남은 작업은 [현재 상태](../../CURRENT_STATE.md)를 따른다.

## 실행

처음 설치할 때는 [Windows 설치 안내](../../docs/INSTALL_KO.md)를 따른다. 기존 설치에서 저장한 모델을 열려면 저장소 폴더의 PowerShell에서 실행한다.

```powershell
./scripts/start_cae_pre.ps1 -Source 'C:/models/editable.FCStd'
```

FreeCAD가 다른 위치에 설치돼 있다면 경로를 지정한다.

```powershell
./scripts/start_cae_pre.ps1 -FreeCADRoot 'C:/Tools/FreeCAD' -Source 'C:/models/editable.FCStd'
```

실행 스크립트는 기존 로컬 연구 서비스를 시작하거나 연결한 뒤 FreeCAD 창을 연다. FreeCAD 실행 파일과 사용자 모델은 Git에 포함되지 않는다. `-PrepareOnly`는 실행 준비만 하며 창을 열지 않는다. 조작 순서와 실제 화면은 [사용 안내](../../docs/USER_GUIDE_KO.md)에서 확인한다.

## 재료와 기본 조건 편집

**해석 모델 → 재료**에서 기본 재료를 고르고 **FreeCAD에서 재료 편집**을 누른다.
탄성 물성과 단위는 FreeCAD 설정창에서 바꾼다. 소성 곡선과 기하 비선형 설정은 기존
CAE Lab 페이지에 남아 있다.

**영역과 조건**에서 고정·힘 조건을 고르고 **FreeCAD에서 조건 편집**을 누른다.
힘의 크기만 바꿨다면 추가 대상 확인은 필요 없다. 적용 면이나 방향을 바꿨다면 3D에서
확인한 뒤 **현재 적용 대상 확인**을 누른다. 형상이 바뀐 경우에는 현재 면을 다시 선택해
**선택한 면으로 변경**한다. 힘 방향도 복구해야 하면 **복구할 힘 방향**에서 새 모서리 영역이나
면의 법선을 명시적으로 고른다. 지정 변위의 값은 기존 FreeCAD 속성창에서 편집한다.

이 전환의 Qt 동작·대상 검사와 실제 FreeCAD 설정창의 직접 조작 확인은
[현재 상태](../../CURRENT_STATE.md)에서 구분한다.

## 공개 지그의 입력·계산·결과 연결 확인

`scripts/check_native_fixture_delivery.py`는 기존 `roller_support`와 FreeCAD의 실제
Tasks·Gmsh·CalculiX writer, 기존 계산 서비스·Runner·ParaView를 잇는 재현용 확인이다.
매번 새 폴더를 사용하고, 실행한 native 프로세스와 자식만 Windows Job으로 정리한다.

```powershell
python scripts/check_native_fixture_delivery.py `
  --root runs/native-fixture-check-new `
  --source-python '<cadquery가 있는 기존 Python>/python.exe' `
  --freecad-root '<FreeCAD 설치 폴더>' `
  --pvpython '<ParaView 설치 폴더>/bin/pvpython.exe'
```

같은 확인에서 이미 보존한 메시를 다시 생성할 필요가 없다면
`--prepared-source runs/<기존 확인>`으로 그 `working.FCStd`와 원 생성 기록을 복사해
이어 쓴다. 원 파일은 덮지 않으며 새 작업 폴더에 복사본의 SHA256과 출처를 기록한다.

조건은 연결 확인용 등방성 재료 E=1000 MPa, ν=0.25, 바닥 고정, 새들 면의 전역 −Z
힘이다. 힘은 `10 N`, `20 N`처럼 단위를 명시한다. FreeCAD의 원 `Force.Value`는
N 값이 아니므로 외부 호출에서는 `Force.getValueAs('N').Value`로 읽는다.
20 N 편집 취소 시 10 N을 유지하고, 수락 뒤에는 새 입력·새 실행을 만든다.

곡면 하중의 요청값과 실제 절점 하중 합력은 별도로 기록한다. 설치된 native writer는
CAD 곡면 면적과 메시 면적을 이용하므로 두 값이 다를 수 있다. 이 확인은 원 writer를
수정하거나 힘을 보정하지 않는다. 이 확인의 보존 합력 오차 1e-8 N 기준을 넘으면 수치
판정은 FAIL로 남기며, 작업 연결의 성공과 공학 적합성 UNKNOWN을 구분한다.
메시 Jacobian·구속·native 표와 deck·원본 hash 검사는 계속 실행 관문이다.

결과 비교는 같은 성분·mm 단위·정적 진행값 1을 사용한다. 절점 ID·좌표·요소가 모두
같을 때만 절점 차이를 만들고, 다르면 나란히 보기만 남긴다. 저장한 Pre/Post를 새
프로세스에서 다시 열 때 계산을 재실행하지 않는다. 단계별 응답과 원 입력·출력은
확인 폴더의 `delivery.json`, native 실행 로그, 각 저장 프로젝트에 남는다.

## 메시 비교 명령 연결

**CAE 작업 → 메시 품질 비교…**에서 현재 메시와 보관된 이전 메시의 품질 통계를 비교한다. 메시가 여러 개라면 모델 트리에서 현재 메시 하나를 선택한다. [사용 순서](../../docs/USER_GUIDE_KO.md#메시를-다시-만든-뒤-품질-비교하기)를 참고한다. 선택 요소 격리·확대는 아직 개발 중이다.

이 창과 외부 호출은 같은 읽기 전용 공통 명령 `pre.fem.mesh_compare`를 사용한다.

호출 대상 `target.object_id`는 현재 메시이며, 인수 `history_id`는 같은 메시의 완료된 재메시 기록이다. `mesh_sha256`에는 직전 품질 조회에서 받은 현재 메시 값을 전달한다. 오래된 기록을 선택해도 현재 메시와 그 기록의 보관본을 비교한다.

반환값은 이전/현재 요소 수, 불량 요소 수, 요소별 최소 Jacobian의 범위·분포와 변화값이다. 기존 품질 정의와 한계를 그대로 사용한다. 분포 구간 경계가 다르면 구간별 차이를 만들지 않는다. 재메시 전후 요소 번호의 일치를 공간상 같은 요소로 해석하지 않으며 공학적 적합 판정을 내리지 않는다.

비교는 모델·화면·저장 기록을 바꾸지 않는다. 현재 메시가 바뀌면 품질을 다시 조회하고, 보관본이 삭제되거나 기록과 달라졌다면 다른 기록을 선택해야 한다.

관련 검사는 `tests/test_pre_mesh_quality_compare.py`, `tests/test_pre_bridge.py`, `tests/test_pre_mesh_compare_panel.py`, `tests/test_pre_mesh_compare_entry.py`에 있다. Qt 대역 검사와 실제 FreeCAD 확인 범위는 [현재 상태](../../CURRENT_STATE.md)에서 구별한다.
