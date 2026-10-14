# native Post 종료 관문 — PRO-POST-NATIVE-EXIT-20261015-01

이 인도물은 실제 C++ GUI plugin, 명시적 C ABI, Python owner callback, 공통 종료 관문,
전용 검사와 설치 소스다. Windows에서 빌드한 DLL이나 실제 ParaView 합격 증거는 아니다.
현재 Windows runtime에는 SDK가 없으므로 소스 인도와 제품 native 수용 검사를 구분한다.

## 사용자가 보게 될 동작

관리 Post에서 File > Exit, 해당 QAction의 Ctrl+Q, X, Alt+F4는 stock main window의
같은 QCloseEvent에 도달한다. plugin은 그 창에만 event filter를 설치한다. 미저장 뷰,
Properties, unchecked 값, Properties 편집기의 미완성 입력에 대해 한글
`저장 / 저장 안 함 / 취소`를 표시한다. 기본/Enter 및 Escape는 취소다.

저장은 기존 `Controls._save → Owner.save_project`만 사용한다. 프로젝트 원본 연결과
manifest가 성공한 saved_revision/generation을 확인한다. Save Data, Save State,
이미지 export를 프로젝트 저장으로 취급하지 않는다. 미적용 Properties나 `1e`처럼
validator를 통과하지 않은 입력은 저장 전에 막고 적용/되돌리기를 안내한다. 값을
자동 적용하거나 고치거나 지우지 않는다. 저장 안 함은 같은 상태임을 다시 확인한
뒤 닫는다. 취소, 실패, UNKNOWN, 대화 중 변경, 진행 작업은 창과 입력을 남긴다.

허용은 닫힘과 다르다. stock close handler가 뒤에서 취소하면 owner/timer/broker를
유지한다. 실제 허용된 Hide 또는 이미 발생한 파괴/종료의 cleanup에서만 기존
GuiDispatch.close를 호출한다. 파괴/종료 통지는 취소 가능한 저장 관문이 아니다.

## 파일 소유와 통합 순서

`product.patch`는 신규 파일만 추가한다. `integration.patch`는 team-current의
`apps/desktop_post/native_controls.py`와 `bridge.py` 두 파일만 최소 연결한다.
startup.py, workspace.py, commands.py, Core/registry, dynamic, ReportPNG와 다른 팀
파일은 수정하지 않는다. 기존 `_tick`의 실제 heartbeat, queued mutation 정지,
진행 작업 보호, broker closed receipt 및 observer/timer 정리 코드를 재사용한다.
Report의 existing Workspace.export PNG 반환 계약도 그대로다.

패치는 원 ZIP의 base가 아니라 **team-current overlay를 적용한 상태**를 기준으로 한다.
인도 ZIP의 `input-manifest.json`에 실제 기준 파일 해시를 기록했다. root 통합자는
현재 동시 작성본과 비교한 뒤 적용한다. 명시된 upstream commit과 이 패치 검사용
로컬 git baseline을 같은 커밋이라고 취급하면 안 된다.

```powershell
git apply --check product.patch
git apply --check integration.patch
git apply product.patch
git apply integration.patch
python -m pytest -q tests/test_post_native_exit.py tests/test_post_native_controls.py tests/test_desktop_post_bridge.py
```

두 patch를 적용하는 것과 `product/`의 동일 신규 파일을 복사하는 것은 대안이다.
두 방법을 중복 적용하지 않는다. 사용자가 Git을 수작업 운영해야 한다는 요구가
아니라 root/Codex 통합 담당의 적용 절차다.

## 설치와 실행

BUILD_WINDOWS_KO.md에 따라 정확한 SDK로 plugin을 빌드하고 runtime identity manifest를
생성한다. `CAE_POST_EXIT_PLUGIN`은 생성한 CaePostExit.dll의 절대 경로,
`CAE_POST_PARAVIEW_ROOT`는 해당 runtime의 루트로 설정한다. 기존 `CAE_POST_HOME`,
`CAE_POST_PROJECT`, `CAE_POST_SERVICE_URL`와 startup 경로는 바꾸지 않는다.

```powershell
$env:CAE_POST_EXIT_PLUGIN = 'C:\cae-build\artifact\CaePostExit.dll'
$env:CAE_POST_PARAVIEW_ROOT = 'C:\cae-tools\ParaView-6.2.0-matched'
# 이후 기존 관리 Post 열기 명령을 사용한다.
```

plugin은 먼저 공식 `paraview.simple.LoadPlugin(..., remote=False)`로 로드된다.
그 다음 자신의 C 함수만 ctypes로 연결한다. Qt/PythonQt/PySide/PyQt를 추가하지
않는다. native thread/pid/mainWidget/registration/session 일치 및 버전을 확인한다.
다른 프로세스, 별도 script editor, dialog에는 save/close filter를 설치하지 않는다.

plugin이 없거나 불일치하면 Python 출력/launch 로그에 **전체 종료 보호 미설치**와
`File > Exit/Ctrl+Q는 보호되지 않습니다`를 명시한다. 기존 Windows X/Alt+F4/Ctrl+S와
저장 매크로의 제한된 동작만 남는다. 전체 native 보호가 설치됐다고 표시하지 않는다.

## 제출 시점의 정확한 상태

Python 검사는 fake ParaView/owner와 실제 callback adapter를 검사했다. C/C++ 검사는
Qt 없는 transaction과 실제 C→Python CFUNCTYPE 왕복을 컴파일/실행했다. 최종 focused Python 결과는 76 passed/1 skipped, C/C++ core는 2/2 passed다. 상세 결과는
ZIP의 evidence에 있다. 별도 retained save 회귀 테스트는 첨부에서 test_retained_law_responses
helper가 빠져 collection error였으며 성공으로 세지 않았다. Qt harness 소스는 작성했지만 Qt6.9 SDK가 없어 실행하지 않았다.
ParaView SDK configure도 실제 시도했으며 ParaViewConfig 부재로 실패한 로그를 보존했다.
Windows/MSVC plugin 컴파일, 실제 네 종료 입력, 재열기, 정상/좁은 native 화면 캡처,
Qt 고DPI 한글 배치 수용 검사는 **NOT_RUN**이다. 이를 완료로 보고하지 않는다.

Pro 입력 첨부에는 `tests/test_native_check.py`만 있고 그 대상인
`scripts/native_check.py` 본체가 없었다. 현재 Windows 저장소에는 기존 실행기가 있으며,
전용 Windows 검사 wrapper는 이 파일이 없는 경우 프로세스를 시작하지 않는다.
공통 runner를 임의로 재작성하거나 사용자
ParaView를 이름으로 찾아 종료하는 우회는 넣지 않았다.
