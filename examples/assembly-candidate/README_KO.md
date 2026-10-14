# 선택 자세 모델의 Windows 확인

02 M4가 적용된 통합 작업 폴더에 이번 `product.patch`를 반영합니다. 기존 FreeCAD 1.1.4·Gmsh와 `scripts/native_check.py`를 사용합니다. 아래 Windows 실행은 이 제출 환경에서는 **미실행**입니다. WSL, 새 solver, 유료 API나 제품 의존성을 추가하지 않습니다.

## 보존한 원 조립에서 이어가기

Codex의 Windows 작업 폴더에서 실행합니다. 실행 파일은 실제 설치 경로로, 출력은 **아직 없는 짧은 경로**로 지정합니다.

```powershell
python examples/assembly-candidate/run_native_correction.py `
  --freecad "C:\Program Files\FreeCAD 1.1\bin\FreeCAD.exe" `
  --source tests/fixtures/assembly_pose_native/source.caepre `
  --selection tests/fixtures/assembly_pose_native/receipt.json `
  --retained-draft tests/fixtures/assembly_pose_native/draft.caepre `
  --output C:\cae\m4a3
```

원 source/draft/selection 파일의 hash를 비교하고 작업 사본만 엽니다. 보존된 accepted 운동 결과를 사용하며 운동을 새로 계산하지 않습니다. 원 조립과 실패 자료를 덮거나 준비 실패를 READY로 바꾸지 않습니다.

## 세 단계

**prepare:** 저장 프레임을 독립 모델로 만들고 네 반복 부품 각각에 서로 다른 재료, 전역·국부 크기와 실제 Face1~Face4 고정조건을 명시적으로 지정합니다. 네 대상의 Gmsh 생성 성공과 정확한 mesh.Shape·binding을 확인하고 `p/edited.caepre`에 저장합니다. 기구 ground의 변환이 아니라 검사에서 직접 지정하는 면 조건입니다.

**cold-edit:** 새 FreeCAD에서 `edited.caepre`를 엽니다. 먼저 네 대상/재료/조건 면/국부 크기/binding/노드·요소 내용과 저장값이 일치하고 native 재계산이 없는지 확인합니다. 그 뒤 기존 적용 명령으로 네 대상 모두의 E/ν, 최소·최대 메시 크기, 국부 크기와 조건 면을 변경합니다. 같은 mesh/material/condition/refinement 객체를 편집하는지, 지정한 값이 실제로 반영되었는지 검사하고 **다른 파일** `p/cold-edited.caepre`에 저장합니다.

**cold-resaved:** 다시 새 FreeCAD에서 `cold-edited.caepre`를 읽습니다. 둘째 단계에서 바꾼 값과 정확한 부품/면 대응, 유지된 메시 내용/binding을 대조하고 읽기 중 재계산이 없음을 확인합니다. 첫 파일을 다시 읽어 통과한 것으로 대신하지 않습니다.

편집 과정의 명시적 native 재계산과 cold read의 무재계산은 구분됩니다. 둘째·셋째 단계에서 Gmsh를 다시 돌리거나 FEM solver를 실행하지 않습니다. 새 크기 입력은 저장하지만 **이전 메시가 새 크기로 다시 생성된 것은 아닙니다.** `mesh_regeneration=NOT_PERFORMED`로 기록합니다. 입력을 적용하는 GUI 클릭과 미적용 입력 보호는 별도 native 사용성 확인입니다.

## 결과와 정리

최상위 `native-owned-summary.json`은 세 단계, 원파일 보존, 실제 프로세스 결과를 종합합니다. 각 `<단계>-process/native-check.json`, stdout/stderr 로그는 **기존 공통 실행기**가 남깁니다. M4가 공통 파일을 교체하거나 두 번째 Windows Job을 만들지 않습니다. 자기 호출의 FreeCAD와 자식 Gmsh만 정리하고, 사용자 FreeCAD/ParaView는 종료하지 않습니다. timeout·정리 미확인·다른 PID의 결과는 PASS로 처리하지 않습니다.

`p/native-check.json`은 최초 편집, `p/cold-check.json`은 둘째 프로세스의 편집 전 읽기, `p/cold-edit-check.json`은 실제 변경·적용·재저장, `p/cold-resaved-check.json`은 셋째 프로세스 읽기입니다. native 실행 전 성공 파일을 만들지 않습니다. 실패하면 가능한 새 수정 사본을 별도 파일로 남기고, 저장 실패도 결과에 표시합니다. 재실행에는 새 출력 경로를 사용합니다.

## 일반 GUI 작업

**운동 → 저장 결과 → 프레임 → 해석 모델 만들기 → 부품 선택 → 메시·재료·면 조건 → 저장** 순서입니다. 준비 실패·취소 사본은 첫 부품이 정상이더라도 M4 FEM 버튼이 켜지면 안 됩니다. native CAD 편집과 저장은 가능해야 합니다. 정상 READY 모델은 아직 빈 재료나 메시 설정만 있어도 초안 저장할 수 있습니다.

저장 파일을 새 FreeCAD에서 열고 각 부품의 재료 값, 전역/국부 크기, 실제 면 조건을 바꾸어 적용한 뒤 별도 저장합니다. 그 파일을 다시 열어 변경값과 대상을 확인합니다. 원 조립의 CAD/자세/저장 결과가 변하지 않아야 합니다. 원부품 치수를 바꾸는 경우 기존 메시·면 조건을 자동 재승인하면 안 됩니다.

기존 `CreateNestedSliders.FCMacro`는 새 공개 조립을 만드는 선택지이고, 위 보존 source 재현에서는 실행하지 않습니다. `CheckSelectedPose.FCMacro`, `CheckSelectedPoseWithMesh.FCMacro`, `CheckColdReopen.FCMacro`는 기존 용도로 유지합니다. 전체 교정·소유 프로세스 정리 확인에는 위 세 단계 실행기를 사용합니다.

## 작은 회귀

```powershell
python -m pytest -q -rs tests/test_assembly_pose_candidate.py tests/test_assembly_pose_native_correction.py tests/test_assembly_pose_kernel.py tests/test_assembly_pose_admission.py tests/test_assembly_pose_cold_edit.py tests/test_assembly_pose_owned_runner.py tests/test_assembly_pose_panel.py
```

OCC 또는 Qt가 테스트 환경에 없으면 해당 검사는 skip입니다. Python/double 통과를 Windows FreeCAD·Gmsh·GUI·실제 cold 프로세스 통과로 세지 않습니다. 일반 FEM 공통 admission 연결은 Codex/Sol의 통합본에서 별도로 확인합니다.
