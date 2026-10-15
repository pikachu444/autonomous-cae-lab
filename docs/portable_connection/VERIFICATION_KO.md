> C1 기록은 아래에 보존합니다. 현재 C2 추가 내용은 [C2_VERIFICATION_KO.md](C2_VERIFICATION_KO.md)을 참조하세요.

# C1 실제 검사와 미실행 구분

## 최종 검사의 범위

결과 원문은 인도 `verification/`의 log/XML/JSON이다. 전용 소스와 공통 patch를 새 폴더의 첨부 원본 및 current-common-context에 재적용한 뒤 동일 범위를 다시 실행했다. main의 전체 제품 test suite 통과로 확대하지 않는다. 서로 겹치지 않는 최종 검사 그룹 합계는 **120 passed / 3 skipped**이며, 그룹별 실제 기록을 우선한다. 숫자는 Qt 미실행을 통과로 바꾸지 않는다.

| 그룹 | 실제 최종 결과 | 범위 |
| --- | --- | --- |
| baseline-regression | 62 passed | 기존 portable/graph/HTTP 회귀. 명시 saved_only 제외 검사 유지 |
| c1-acceptance | 33 passed / 2 skipped | C1 core31 + real HTTP2; 기존·새 Qt 두 모듈 collection skip |
| common-regression | 25 passed / 1 skipped | 기존 native command/input 경계; 선택 MCP 미설치 skip |

표의 카운트는 해당 결과 XML과 `test-summary.json`으로 대조한다. 의도적 중복 ZIP member 검사에서 zipfile 경고 하나가 있을 수 있다. 원문 실패/중단 로그는 `verification/development/`에 별도 보존하고 최종 성공으로 덮어쓰지 않는다.

## 실제 완료한 파일·owner·전송 검사

Material saved E와 다른 acknowledged E를 동시에 보존하고, Data의 저장 후 추가 원자료/CSV 가져오기 성공·실패 및 invalid acknowledged payload, 두 Numerical 문서의 실제 개별 ID·Material/Data refs·invalid Plan을 만들었다. 예제 원 보관소를 삭제하고 한글·공백 폴더로 옮긴 뒤 별도 새 프로세스에서 saved base와 dirty acknowledged draft, Undo/Redo/generation, MPa/s 및 UNKNOWN/blank/invalid를 검사했다. 그 owner의 edit→Undo→save를 실행했으며 reopen jobs=0/provider 미생성을 확인했다. 성공/실패 각2건은 실제 CSV import이며 물리 솔버가 아니다.

원 snapshot, 원 receipt, retained source/result bytes를 검사했다. 기존 saved-only, acknowledged-only(아직 saved head가 없는 문서), 저장되지 않은 중간 Material 입력을 가리키는 Plan Undo의 exact 완료 receipt 증거, 결과 noncurrent, missing/stale/refused draft, 잘못된 source scope/result/kind/input을 다뤘다. acknowledged 보존 컨테이너를 fake saved revision으로 노출하지 않고, 실제 후속 owner.save는 정상 saved로 읽는 검사도 포함한다.

실제 관계 추가→preview/취소 무효과→영향→명시 repair/unlink→owner Undo, stale source/target CAS 거절·선택 보존, cloned store 동일 ID 거절을 검사했다. request Plan source/model_source와 기존 Evaluation stage ref도 기존 owner 명령으로 변경하고 saved base/도메인값 보존을 검사했다. 자동 unit/field 변환이나 unsupported physics 관계는 거절했다.

배치 JSON에 선택/좌표/필터/panel을 저장하고 다른 창 역할의 stale view CAS 거절, 사본의 새 ID 대응, 이동 뒤 별도 프로세스의 exact refs/layout 복원을 검사했다. graph/layout-only 동작이 Material/Data/Plan 파일 hash와 결과를 바꾸지 않는 것을 확인했다. 실제 Qt drag는 여기서 실행하지 않았다.

HTTP 검사는 실제 loopback 서버와 Client, 별도 CLI 프로세스다. 대용량 검사는 **18,000,012-byte** 합성 CSV를 허용된 local root에서 명시 등록→Data save→HTTP metadata inspect/create→두 retained source의 원본 동일 SHA→verify READY로 확인한다. 원본 불변, JSON에 bytes/base64 미포함, 일반128 KiB/upload16 MiB/create8 MiB 거절을 확인했다. 20 GiB/100000 files의 한도 전체 및 대용량 native campaign을 수행하지 않았다.

Windows의 실제 raw name 문제는 ZipInfo constructor를 우회해 raw filename을 넣는 fixture와 normalized reader 대역을 분리했다. 제품은 orig_filename의 raw POSIX spelling과 filename 일치를 preflight에서 검사하며 목적지 생성 전에 거절한다. 실제 Windows C1 런타임에서 다시 실행한 결과라고 표기하지 않는다. 경로 탈출을 실증한 적도 없다.

## 기존 Windows 증거를 읽은 결과

`input-evidence/acceptance-windows.md`는 사용자가 제공한 기존 인도 실제 기록이다. 최초 lock helper/overlay 준비 문제, corrected 전체180초 timeout, focused14pass1fail의 raw ZIP 문제를 구분한다. Qt6.9.1 baseline6pass/후속2pass 및17,825,804-byte local input 성공은 기존 코드에 대한 증거이지 새 C1 GUI/대용량 검사의 통과 수치가 아니다. 이 수치는 위120에 더하지 않는다.

ACTIVE `controller.lock`만 size/mtime을 비교하는 정확한 Windows fixture 교정을 유지했다. 나머지 자료는 full hash다. 검사 폴더의 common4 준비 오류를 제품 버그로 계산하지 않았고, root main을 변경했다고 주장하지 않는다.

## NOT_RUN / NOT_COMPLETE

이 컨테이너는 Linux이며 PySide6가 없다. 기존·새 Qt 두 모듈은 collection skip, **QWidget/QTest NOT_RUN**이다. C1 중 Qt 설치나 다운로드를 하지 않았다. C1의 two-size dialog, Esc/실제 modal buttons, 메뉴·Tab·키보드, 그래프 드래그·새 창 배치 복원, 한국어 glyph/focus, close/error 동작을 Windows Qt6.9.1에서 실행하는 검사를 코드로 인도한다. 정적 AST/compile 성공을 이 결과로 대체하지 않는다.

```powershell
$env:QT_QPA_PLATFORM = "windows"
$env:QT_CAPTURE_DIR = "D:\공개 검증\C1 Qt 캡처"
python -m pytest -q tests/test_connection_window_qt.py tests/test_connection_window_c1_qt.py -ra
```

원래 제공된 `examples.connection_window_check`는 baseline용이다. C1의 새 dialog/관계/배치 확인에는 위 새 Qt 모듈도 실행해야 한다. QTest 성공과 OS 실제 mouse/native FreeCAD·ParaView activation은 별개다. Windows owned-job cleanup과 native activation, 전체 설치/WSL, 물리 계산/공학 승인, global CLI/MCP dispatch 캠페인은 여기서 수행하지 않았다. 선택 MCP 패키지 부재로 기존 검사1개를 skip했다.

개발 중 크게 합친 몇 번의 검사 호출은 실행 wrapper의 제한으로 끝나 완료 XML이 없었다. NOT_COMPLETE로 보존하며 전체 성공이라고 세지 않는다. 이후 세 그룹을 나눠 각각 종료 코드0/XML을 얻은 결과만 합산한다. 최초 saved-only 기대값, 새 fixture의 tuple 응답 접근, header 거절 뒤 urllib BrokenPipe 등 개발 중 실패와 교정을 기록한다. 실패한 실행을 성공 로그로 바꾸지 않는다.

재적용 baseline은 한 번 62개 assertion 통과/XML 생성 후에도 wrapper 종료 제한에 걸렸다. 이 실행은 `development/current-baseline-exit-timeout.*`로 보존했으며 정상 종료 수치에 쓰지 않았다. 이후 환경에 설치된 제품 외 tracing/reporting pytest plugin의 자동 로딩을 끈 상태(`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1`)에서 같은 built-in pytest 검사/fixture를 실행했고 세 그룹 모두 **실제 프로세스 종료 코드0**을 확인했다. 종료 지연의 정확한 원인 플러그인은 확정하지 않았다. 제품 코드·assertion·파일 검사·작업 정리를 생략한 것이 아니다. 최종 그룹마다 `*-process.json`에 명령·환경·실제 종료와 시간을 기록했다. 이 조치는 Linux 검사 환경 설정이며 Windows 제품 설정을 변경하지 않는다.

## 재현 명령

```powershell
$env:PYTEST_DISABLE_PLUGIN_AUTOLOAD = "1"
python -m pytest -q tests/test_portable_project.py tests/test_connection_graph.py tests/test_portable_connection_http.py --junitxml=baseline-regression.xml
python -m pytest -q tests/test_portable_connection_c1.py tests/test_portable_connection_c1_http.py tests/test_connection_window_qt.py tests/test_connection_window_c1_qt.py --junitxml=c1-acceptance.xml
python -m pytest -q tests/test_native_commands.py tests/test_workbench_native_inputs.py --junitxml=common-regression.xml
python -m examples.portable_connection_c1_public --output "D:\공개 검증\새 C1 파일 검사"
```

공개 ZIP을 실제로 다시 풀어 별도 cold-check 프로세스로 확인한 결과는 `public-archive-check.json`에 남긴다. `package-check.json`은 ZIP 실존·크기·CRC·source bytes·패치 재적용을 확인하는 산출물 검사이며 제품 전체 기능이나 물리 승인이 아니다. 모든 인도 결과의 engineering_release는 **NOT_RELEASED**다.
