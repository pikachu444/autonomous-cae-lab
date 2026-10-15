# 여러 구동 관계 공개 예제

이 폴더의 Python/FCMacro는 **작성한 소스**다. 인도 시점에 Windows/FreeCAD 실행을
완료한 결과 파일은 없다. reference-oracle.json도 native 결과가 아니라 사용자가
전달한 독립 산술 기대값이다. 바이너리 모델/이미지를 가짜 결과로 넣지 않았다.

## 기존 native 창에서 편집

product.patch와 integration.patch를 순서대로 통합한 저장소에서 FreeCAD 1.1.4 GUI로
`create_relations.FCMacro`를 연다. ground 한 개와 다섯 독립 체인을 만든다. A/B/C는
각각 Revolute 하나, L/X는 각각 Slider 하나로 지지대에 연결된다. moving Link는
모두 같은 rod 원형을 참조하지만 서로 다른 occurrence다. 같은 moving body에
모순되는 관절을 여러 개 부착하지 않는다.

macro는 native CAD를 만들고 관계식을 적용할 뿐 계산하지 않는다. 임시 owner는
즉시 해제하고 기존 CAE 연결이 문서를 발견하게 한다. 별도 패널/브로커/서비스를
시작하지 않는다. 기존 **조립 운동 → 시간과 구동**에서 C를 선택하면
`amplitude*sin(A)+B`, amplitude 30 deg, X를 선택하면 `gain*A+L`, gain 2 mm/deg가
보인다. 적용/계산/저장/닫기는 기존 메뉴를 사용한다. 범위와 오류 복구는
[사용법](../../docs/MOTION_RELATIONS_KO.md)을 따른다.

조립은 처음부터 문서 전체 좌표에 이동·회전되어 있다. C/X의 로컬 [20,0,0] 점을
추적하므로, joint coordinate뿐 아니라 world transform의 일치도 검사할 수 있다.
L/X는 좌표명이며 Slider의 운동 방향은 관절 로컬 Z다. 이 rig는 접촉/충돌/FEM
물리 검증용이 아니다.

## 자기 프로세스만 사용하는 Windows 검사

기존 저장소 Python 환경에서 다음을 실행한다. 출력은 **새 빈 폴더**여야 한다.
기존 사용자 FreeCAD 창은 사용하지 않는다. 실행 파일 경로는 설치 위치로 바꾼다.

```powershell
python examples/assembly_relations/native_check.py `
  --freecad 'C:\Program Files\FreeCAD 1.1\bin\FreeCAD.exe' `
  --output-dir 'C:\CAE-checks\m1-relations-r01' `
  --timeout 180
```

wrapper는 기존 `scripts/native_check.py:run_native_check(command,output_dir,
timeout_seconds,cwd)`만 호출한다. 새 Job/scheduler/WSL을 만들지 않는다. 이 기존
runner가 각 invocation의 suspended root를 자기 Windows Job에 넣고 성공/실패/
timeout에서 그 Job만 정리한다. 프로세스 이름이나 창 제목으로 종료하지 않는다.
각 phase는 별도의 user.cfg/system.cfg를 사용하며 single-instance 옵션을 쓰지
않는다. child는 실제 자신의 UserParameter 경로와 시작 문서 부재를 확인한 경우에만
계산하고 자기 event loop를 종료한다. 이 확인이 안 되면 사용자 창을 닫지 않는다.

phase는 세 개다. **compute**는 선형 관계, A=60으로 바꾼 관계, 비선형 관계를 실제
native로 계산하고 원 기대값의 다섯 시각을 대조한다. A=60일 때 X도 같은 gain을
유지하므로 125*time mm가 되는 것을 추가 검사한다. 새 시각 배열을 추정해서 붙이지
않고 기존 pinned native clock 규칙/프레임 수 대조를 사용하며 첫 design frame의
시각은 None이다. 실제 getter에서 solver time 배열을 읽었다고 주장하지 않는다.

각 frame은 native updateForFrame으로 직접 다시 읽고 보존 pose와 비교한다.
JCS의 상대 회전/이동을 측정하며 C/X의 실제 world point도 비교한다. tolerance는
입력의 1e-6을 유지하고 mismatch에 맞추어 늘리지 않는다. 기존 성공과 다음 실패/
입력은 별도로 보존한다. 유효 선택을 valid.caepre, `1e`/미완성 식을 raw.caepre로
기존 Project.save를 통해 저장한다.

다음 **valid**와 **raw**는 각각 새 프로세스/owner로 원 .caepre를 기존 reader로
working copy에 연다. 원 관계, 선택, 모든 원 결과/경로를 확인하고 읽기만으로
metadata가 변하지 않는지 검사한다. valid는 보존 frame을 계산 없이 본다. raw는
새 계산/자세/재생/채택이 모두 차단되는지 확인한다. 마지막에 명시적으로 수정·적용·
다시 저장하고 원 .caepre의 SHA와 원 결과가 그대로인지 확인한다. 원본은 덮지 않는다.

`acceptance.json.completed=true`만 따로 보지 않는다. 각 phase의 actual result,
process PID, exit code, timeout, cleanup=job_empty, `job/native-check.json`을 함께
대조한다. 보고서 없음, PID 불일치, UNKNOWN, cleanup 미확인은 실패다. 실패 뒤에는
같은 폴더로 재실행하지 않는다. 기존 로그/실패 모델을 남기고 새 빈 폴더를 사용한다.

## 이 검사로 완료하지 않는 항목

위 스크립트는 수치·native API·저장 재열기 경로다. 실제 Windows 메뉴 클릭, source
picker의 Esc/단위 확인, 입력 중 Ctrl+S, 늦은 응답, 다른 조립 선택, hide/show,
Undo/Redo와 두 너비의 가독성은 전용 Qt 검사 및 root의 실제 GUI 수용으로 확인한다.
그 UI를 클릭했다고 자동 보고하지 않는다.

첨부 snapshot에는 기존 두 단계 가동 조립의 native 실행 설명과 API fixture가
있지만 재사용 가능한 native rig 생성 파일은 들어 있지 않다. 이 작성분은
`test_pre_motion_nested_assembly.nested` fixture를 재사용하여 깊은 관절 path 변경/
재선택과 반복 Link 분리를 검사했다. 기존 M2 native 캠페인을 반복한 것이 아니다.
root가 보유한 실제 두 단계 모델에서는 그 관절을 이 editor의 source로 선택하여
같은 경로/복구를 작은 추가 수용으로 확인한다. 부족한 과거 transform을 새 결과처럼
채우거나 기존 자료를 소급 수정하지 않는다.
