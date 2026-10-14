# 종료 관문 검수표 — 실행 증거가 없는 행은 NOT_RUN

## 검사 층위

A. Python 단위검사: owner fake/native API doubles, actual CFUNCTYPE adapter, 상태/저장
실패/재진입/late validation/재시도/three lifecycle/미완성 draft/manifest 거부 검사.
B. C/C++ core: CloseTransaction 및 실제 C→Python ABI. Qt가 없어서도 수행 가능.
C. Qt6.9 harness: 실제 QCloseEvent/QAction/Ctrl+Q/Windows SC_CLOSE 및 자기 HWND의
Alt+F4 system-key message, stock 및 late veto, modal, 범위, 한글 기본 focus,
narrow/normal QWidget grab 캡처. Windows MSVC로 빌드·실행했다. 최초 XML 12 case
중 2개 입력 전달 검사는 실패했으며, 하네스 전달 교정 뒤 그 두 검사만 재실행해
통과했다. 실제 사용자 키보드 입력이나 ParaView의 결과로 세지 않는다.
D. 실제 Windows ParaView6.2: 반드시 아래의 전체 검수표와 새 owner 복구를 확인한다.
A/B 또는 C 결과를 D의 합격으로 바꾸지 않는다. QtTest가 보낸 key event도 물리적
Windows 키보드/비클라이언트 X의 실제 입력 증명과 구분한다.

## 실제 ParaView 입력별 매트릭스

| 실제 입력 | clean | dirty 저장/안 함/취소 | unchecked/미완성 | 실패/UNKNOWN/변경 | 실행 중 | 취소 후 재시도 |
|---|---|---|---|---|---|---|
| File > Exit 실제 QAction | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| 같은 QAction shortcut(Ctrl+Q) | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| 타이틀바 X | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |
| Alt+F4 | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN | NOT_RUN |

소스 확인상 actionFileExit objectName과 shortcut이 존재하지만 메뉴 좌표/영문 label
추정으로 테스트를 통과시키지 않는다. 현재 제공한 실창 check wrapper는 **대화형**이다.
`--route`는 검수자가 수행할 입력의 선언이지 자동 관측 증거가 아니다. 실제 action
경로/keyboard 전달 증거와 캡처는 담당자가 별도 기록한다. Qt harness의 synthetic
경로와 실제 stock ParaView UI 수용 검사를 혼합하지 않는다.

관리 Post는 scratch project에 기존 external/계산 결과를 열어서 준비한다. source는
읽기 전용 원본을 참조할 수 있지만 project_root는 run-dir/scratch 안이어야 한다.
처음/실패 결과/화면 캡처/manifest는 덮어쓰지 않는다. solver 재계산은 하지 않는다.

```powershell
# 기존 root 소유 scripts/native_check.py를 그대로 사용한다.
python scripts/post_native_exit_check.py `
  --paraview-root C:\cae-tools\ParaView-6.2.0-matched `
  --plugin C:\cae-build\artifact-r01\CaePostExit.dll `
  --scratch-project C:\cae-checks\r01\scratch\project.json `
  --run-dir C:\cae-checks\r01 --service-url http://127.0.0.1:8000 `
  --route file-exit --timeout 900
```

script는 기존 Job Object runner로 자기 ParaView 프로세스와 자식만 소유한다.
그 runner가 없으면 launch 전에 ROOT_INPUT_MISSING으로 끝난다. `taskkill /IM`,
Get-Process paraview 전수종료, 사용자의 기존 창 연결은 없다. timeout 후 자기 Job을
정리하더라도 그것을 정상 저장/취소/종료 성공이라고 기록하지 않는다.

native-events.jsonl은 ready status, registration/attempt, BEGIN/VALIDATE/ABORTED/
CLOSED, owner/snapshot, close cleanup 결과를 기록한다. launch-result.json의
REQUIRES_REVIEW는 정상 process exit와 기능 수용이 다르다는 뜻이다.

## 추가 실제 확인

SaveData/SaveState/export는 프로젝트 commit으로 세지 않는다. stock Save State 질문을
켜서 취소하는 경우에도 다음 종료를 다시 묻고 timer/owner가 남는지 확인한다.
upstream Closing flag 경계는 ARCHITECTURE_KO.md를 참조한다.

작업 중단은 native GetPendingProgress 또는 existing command_gate.executing으로
판단하며, 이미 실행 중인 계산에 가짜 CANCELLED 결과를 만들지 않는다. nested dialog
동안 service heartbeat만 실제 tick으로 유지되고 queued mutation은 실행되지 않아야 한다.

열기→취소→재시도→닫기를 세 번 반복한다. 각 active 등록에는 filter=1,
owner/session 하나만 있어야 한다. close 뒤 등록/filter/전용 활성timer와 연결 observer가
0이고 existing interactor timer/source observer/save owner가 해제되어야 한다. broker
closed receipt와 대기 명령 정리는 기존 root 계약으로 확인한다.

같은 저장파일을 새로운 ParaView 프로세스로 열어 native field/component/실제 time/
view/camera/원분석 source와 manifest를 비교한다. 원파일, failed 결과, 동결 모델을
지우지 않는다. 기존 result reader/Workspace restore를 사용하고 새 복구 format을
만들지 않는다. Report PNG contract 회귀 검사는 기존 export 테스트를 재사용한다.

정상 폭과 좁은 native 창에서 한글 세 버튼, text wrapping, Cancel default/Enter/Escape,
Tab focus, Windows 배율을 캡처한다. 별도 unmanaged ParaView와 Python script editor는
original save/close 동작을 유지해야 한다. 같은 프로세스 내 clean editor가
closeAllWindows의 stock 순서로 먼저 닫히는 것은 plugin이 순서를 다시 만드는 대상이 아니다.
