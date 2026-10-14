# E1 셸 제출 검사 기록

요청 `PRO-E1-SHELL-20261014-01`. 기준 커밋 `bbffc70c0752ad39f0933d5c13bc8291a1da8855`.

## 실제로 수행한 검사

- Python 3.13 컨테이너에서 새 제품 모듈·예제·테스트의 `compileall`: 통과.
- 새 셸 회귀: **64 passed, 0 failed, 0 skipped**. 최종 검사 출력은 아래와 같다.

```text
................................................................         [100%]
64 passed in 0.81s
```

숫자/두께 2→3/offset/법선 반전/선택/초안 저장·복구, native 카드 의미 검사, `.12d`/FRD/DAT의 상·하면/내부점 대응, 누락·잘린 필드/변조 거부, 새 실행 폴더 보존, 취소·실패, 검토한 입력의 동일 command 재사용, 온라인·연결 중단 상태의 초안 저장, native 입력·결과 등록을 검사했다. 생성 VTU는 실제 설치된 VTK reader로 읽었으며 Q8 표면 요소와 필드 구성을 검사했다. VTK 읽기는 실제 실행이지만 FreeCAD/CalculiX/ParaView GUI 실행은 아니다.

### 대역과 실제 기준 코드의 경계

실제 전체 저장소 checkout이 아니라, 제출 모듈과 필요한 기준 코드의 제한된 지원 모듈로 실행했다. FreeCAD 문서/속성/transaction/GUI/프로세스는 명시적 대역이며 원자료 FRD/DAT/12d는 **합성 검사 데이터**다. 시험용 `editable.FCStd`는 대역이며 공개 편집 예제로 배포하지 않는다. 공개 예제는 별도 deterministic native 생성기다.

실제 기준 `caelab/native_inputs.py` 전체를 조회·복원하여 Git blob SHA **`0ed1ef1b15d5cda3ba3fccb6c70a2f32332a5aff`**가 일치함을 확인했다. 이 파일에 공통 패치의 해당 hunks를 적용하고 등록 검사 3개를 수행했다. `storage`, `evaluation.file_hash`, process ownership 등 주변 모듈은 제한된 지원 구현/대역이므로 이를 전체 Workbench/JobManager 통합 통과로 해석하지 않는다. 기존 native 숫자 serializer와 FRD record parser의 호출 계약도 기준 소스와 대조했다.

이 대역 지원 폴더는 제품 ZIP에 포함하지 않는다. 통합 저장소에서는 본래 모듈을 import해 아래 명령을 다시 실행한다.

```powershell
python -m pytest -q tests/test_shell_model.py tests/test_shell_edit.py tests/test_shell_controls.py tests/test_shell_results.py tests/test_shell_execution.py tests/test_shell_registration.py
```

## 패치 검사

일반 `git apply --check`에서 처음 발견한 문맥 부족을 수정했다. 최종 패치는 별도 zero-context 옵션을 요구하지 않는다.

- 전체 원본을 확보한 `native_inputs.py`: 일반 `git apply --check --include=caelab/native_inputs.py integration.patch` 통과.
- 공통 9개 파일: 조회한 원문 문맥으로 구성한 검사 fixture에서 일반 `git apply --check`, 실제 적용, 예상 변경 내용 대조 통과. 이 중 나머지 8개 파일은 **전체 원본이 아닌 문맥 fixture**이므로 실제 기준 저장소 전체에서의 적용 검사를 대신하지 않는다.
- `feature.patch`: 새 파일 추가 패치를 빈 적용 디렉터리에 적용한 뒤 모든 제출 파일 바이트를 원본과 대조한다. 이것은 새 파일 패치의 배포 무결성 검사다.

기준 이후 통합 브랜치가 바뀌었다면 Codex는 적용 전 실제 현재 파일에서 `git apply --check integration.patch`를 수행해야 한다. 다른 작성자 파일을 초기화하거나 강제 적용하는 절차는 없다.

## 미수행 / 잔여

FreeCAD 1.1.4 실제 writer, CalculiX 2.22 Windows 실제 계산, `.FCStd` 및 `.caepre` native 저장·닫기·재열기, ParaView native GUI, 실제 한글 글꼴/포커스/좁은 창, 전체 JobManager 취소 후 게시, 기존 NS1/M3 통합 회귀는 미수행이다. `WINDOWS_CHECKLIST.md`가 실제 확인 절차다. 프로그램 실행 성공과 공학적 수치 승인은 별개다.

정확한 표면 적분점 응력·변형률은 **미지원**이다. 제공하도록 작성한 상·하면 S/E는 native FRD 외삽·평균 절점 복원값이다. DAT의 27개 내부 적분점과 별도로 저장하며 E1의 정확한 표면 결과 요구를 완료 처리하지 않는다. 해석 객체 자체를 삭제한 초안을 다른 Analysis로 일괄 이전하는 UI도 범위 밖이며 문서에 복구 경계를 명시했다.

## Git 제출 상태

`codex/shell-user-model-20261014` 브랜치를 요청한 기준 커밋에서 생성하고 그 HEAD를 조회했다. 그 뒤 `create_tree` 소스 쓰기 요청이 도구의 보안 상태 판정 불가로 차단되었다. **새 코드 커밋과 PR은 생성하지 못했다. 브랜치는 기준 커밋 그대로다.** 소스가 게시되었다고 해석하면 안 된다. 다운로드 ZIP, 새 파일 전체 feature.patch, 공통 integration.patch를 대체 제출한다. 다른 브랜치의 변경/초기화/강제 push는 수행하지 않았다.
