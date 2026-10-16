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

## 메시 비교 명령 연결

**CAE 작업 → 메시 품질 비교…**에서 현재 메시와 보관된 이전 메시의 품질 통계를 비교한다. 메시가 여러 개라면 모델 트리에서 현재 메시 하나를 선택한다. [사용 순서](../../docs/USER_GUIDE_KO.md#메시를-다시-만든-뒤-품질-비교하기)를 참고한다. 선택 요소 격리·확대는 아직 개발 중이다.

이 창과 외부 호출은 같은 읽기 전용 공통 명령 `pre.fem.mesh_compare`를 사용한다.

호출 대상 `target.object_id`는 현재 메시이며, 인수 `history_id`는 같은 메시의 완료된 재메시 기록이다. `mesh_sha256`에는 직전 품질 조회에서 받은 현재 메시 값을 전달한다. 오래된 기록을 선택해도 현재 메시와 그 기록의 보관본을 비교한다.

반환값은 이전/현재 요소 수, 불량 요소 수, 요소별 최소 Jacobian의 범위·분포와 변화값이다. 기존 품질 정의와 한계를 그대로 사용한다. 분포 구간 경계가 다르면 구간별 차이를 만들지 않는다. 재메시 전후 요소 번호의 일치를 공간상 같은 요소로 해석하지 않으며 공학적 적합 판정을 내리지 않는다.

비교는 모델·화면·저장 기록을 바꾸지 않는다. 현재 메시가 바뀌면 품질을 다시 조회하고, 보관본이 삭제되거나 기록과 달라졌다면 다른 기록을 선택해야 한다.

관련 검사는 `tests/test_pre_mesh_quality_compare.py`, `tests/test_pre_bridge.py`, `tests/test_pre_mesh_compare_panel.py`, `tests/test_pre_mesh_compare_entry.py`에 있다. Qt 대역 검사와 실제 FreeCAD 확인 범위는 [현재 상태](../../CURRENT_STATE.md)에서 구별한다.
