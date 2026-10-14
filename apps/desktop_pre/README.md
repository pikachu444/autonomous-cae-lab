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

## 메시 비교 명령 연결

개발용 공통 명령 `pre.fem.mesh_compare`는 현재 메시와 보관된 이전 메시의 품질 통계를 비교한다. **비교 창 연결과 선택 요소 격리·확대는 아직 개발 중이다.**

호출 대상 `target.object_id`는 현재 메시이며, 인수 `history_id`는 같은 메시의 완료된 재메시 기록이다. `mesh_sha256`에는 직전 품질 조회에서 받은 현재 메시 값을 전달한다. 오래된 기록을 선택해도 현재 메시와 그 기록의 보관본을 비교한다.

반환값은 이전/현재 요소 수, 불량 요소 수, Jacobian 최소·최대·분포와 변화값이다. 기존 품질 정의와 한계를 그대로 사용한다. 분포 구간 경계가 다르면 구간별 차이를 만들지 않는다. 재메시 전후 요소 번호의 일치를 공간상 같은 요소로 해석하지 않으며 공학적 적합 판정을 내리지 않는다.

비교는 모델·화면·저장 기록을 바꾸지 않는다. 현재 메시가 바뀌면 품질을 다시 조회하고, 보관본이 삭제되거나 기록과 달라졌다면 다른 기록을 선택해야 한다.

관련 검사는 `tests/test_pre_mesh_quality_compare.py`와 `tests/test_pre_bridge.py`에 있다. 이 검사의 통과는 실제 비교 GUI 완료를 뜻하지 않는다. 실제 native 실행 범위는 [전후처리 확인 기록](../../docs/PREPOST_VERIFICATION.md)에 남긴다.
