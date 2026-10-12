# Material Qt 기술 프로토타입

**잠정 기술 검사 산출물**이다. Codex가 기존 실제 Pro v2의 §§6.1–6.4를 바탕으로 만든
별도 편집 가능한 계획 시안이다. 새 실제 Pro의 전체 설계 및 Astra 최종 검토·사용자
설계 수용은 아직 완료하지 않았다. 제품 코드/공통 문서 owner를 수정하지 않는다.
이 폴더의 저장 형식과 Undo는 시안 자체의 상태를 확인하는 용도다.

모든 예측·계수·오차는 **DEMO / SIMULATED UI / 물리 타당성 미검증**이다.
시험 CSV의 수치도 사람이 작성한 예시다. 실제 optimizer·재료 evaluator·solver·AI provider를
호출하지 않는다. 동정 버튼은 Qt 타이머 후 **고정 E=2.4 MPa, b=0.02 MPa**를 반환한다.
RMSE는 그 고정 예측과 선택 관측의 차이를 표시하는 UI 값이며 모델 동정·재료 검증이 아니다.

## 실행과 편집

확인 환경: 사용자 Python 3.13.5, PySide6 6.9.1, Matplotlib 3.10.1.
기존 Research runtime에는 PySide6가 없으며 설치하지 않았다. 추가 지출/패키지 설치 없음.

저장소 루트의 PowerShell에서:

```powershell
& 'C:\Program Files\Python313\python.exe' docs/design/20261012-desktop-planning/qt_prototype/main.py
```

CSV 또는 `.demo.json` 경로를 마지막 인자로 주면 바로 연다.
이미 확인한 비교 화면은 `evidence/review.demo.json`으로 다시 열 수 있다.
이 파일에는 원 CSV 바이트와 후보 네 개가 들어 있어 원 CSV 경로가 없어도 재열 수 있다.

```powershell
& 'C:\Program Files\Python313\python.exe' docs/design/20261012-desktop-planning/qt_prototype/main.py docs/design/20261012-desktop-planning/qt_prototype/evidence/review.demo.json
& 'C:\Users\pikac\AppData\Roaming\Python\Python313\site-packages\PySide6\designer.exe' docs/design/20261012-desktop-planning/qt_prototype/material.ui
```

`material.ui`는 Qt Designer에서 배치/텍스트/도크를 편집하는 원본이다.
`main.py`는 원본을 직접 읽어 표, Matplotlib, 메뉴, 상태 전환을 연결한다.
연결에 쓰는 objectName은 유지한다. 컴파일된 UI 사본이나 별도 웹 호스트는 없다.

## 시연 순서

1. **파일 → 데모 시험 열기** 또는 **CSV 열기**(Ctrl+I). UTF-8/BOM, 쉼표, 머리글을 지원한다.
   원 바이트·SHA256·해석 표를 문서에 보존하며 원파일은 바꾸지 않는다.
2. 변형률/응력 열과 단위를 편집한다. 변형률은 `1`/`%`, 응력은 `Pa`/`kPa`/`MPa`만
   지원한다. `psi`처럼 지원하지 않는 단위는 동정을 막지만 초안 저장/재열기는 가능하다.
3. 표의 Shift 행 선택, 시작/끝 원 행 입력 또는 관측 그래프의 좌우 드래그로 구간을 고른다.
   표와 그림이 같은 구간을 강조한다. 클릭 기준 행과 Shift 클릭/방향키의 구간 기준을 유지한다.
   시험을 바꿨다가 돌아오면 해당 시험의 열·단위·구간이 복원된다. 최소 3행, 증가하는 축이 필요하다.
4. **모델 동정 시뮬레이션 시작**. 약 2초의 진행 상태 후 고정 데모 후보가 생긴다.
   **이번 실행 취소**는 결과 없이 취소 기록을 남긴다. **데모 상태 → 다음 시뮬레이션 실패**는
   실패 경로를 재현하며 체크 해제 후 새 실행으로 복구한다. 후보 ID/입력은 실행마다 새로 남는다.
5. 관측·예측·잔차와 DEMO RMSE를 비교한다. 보존 후보 선택만으로 재계산하지 않는다.
   실행 중 현재 입력을 바꿔도 결과는 출발 입력에 남고 현재 자료/매핑/구간/입력 계수와 다르면 채택을 막는다.
   스크롤 밖 고정 영역에서 선택 후보 번호·상태·채택 가능 여부를 표시한다. 현재 입력 준비 상태와
   후보 완료/실패/취소/중단 상태는 각각 표시한다.
6. **선택 후보 계수 채택…**에서 현재값→데모 후보값 변경을 확인하고 채택한다.
   계수 값은 표에서도 편집한다. **Ctrl+Z / Ctrl+Shift+Z**로 편집/채택을 되돌리고 다시 실행한다.
   빈값·문자·음수 E·NaN/무한값 초안은 입력대로 보존하고 셀과 진단에 오류를 표시한다.
   invalid 계수에서는 시작과 채택을 막으며 저장·재열기는 가능하다.
7. **저장**(Ctrl+S) 후 종료하고 저장본을 새 프로세스로 연다(Ctrl+O).
   원자료·입력·계수·실패/취소/완료 후보·곡선을 다시 보여주며 동정을 실행하지 않는다.
   실행 중 저장본은 재열기에서 `interrupted`로 남고 새 실행을 안내한다.

도크 제목을 끌어 분리/다시 결합하고 경계를 끌어 크기를 바꿀 수 있는 QDockWidget이다.
**창 → 기본 배치 복원**으로 복구한다. 표·그래프 경계도 QSplitter로 조정한다.
좁은 창에서는 시험/매핑/계수/후보 영역을 세로 스크롤하며 실행·취소·채택 버튼은 고정된다.
닫기/문서 교체 시 저장 여부를 확인한다. 실행 중에는 이미 저장했어도 **로컬 DEMO 타이머가
중단됨**을 별도로 알리고 기본 선택은 **계속 보기**다. 중단 후 계속을 선택해도 파일 선택/저장을
취소하면 현재 창의 실행은 유지된다. 저장 실패는 이전 저장본을 유지하며 다른 경로를 안내한다.
`시안 편집 vN`은 이 시안의 편집 번호이며 제품 개정 계약이 아니다. Undo/Redo는 과거 입력의 번호를
보여주지만 새 분기에 이전 번호를 재사용하지 않는다. 다음 번호는 저장본에도 보존한다.

## 확인 근거와 한계

```powershell
& 'C:\Program Files\Python313\python.exe' docs/design/20261012-desktop-planning/qt_prototype/selfcheck.py
```

오프스크린 검사 결과는 [selfcheck-report.json](evidence/selfcheck-report.json)에 있다.
잘못된 단위/매핑 교정, 표·그래프 선택, 타이머 실행/취소/실패/복구, 입력 변경 후 과거 결과
보존과 채택 차단, 채택 Undo/Redo, 저장 오류, 잘못된 저장본 거부, 원바이트/기존 결과 보존,
새 subprocess 재열기(동정 시작 0회), 종료된 진행 기록과 dirty 상태를 확인했다.
Qt 도크 floating/redocking 메서드도 확인했다.

2026-10-12 독립 Astra 지적 교정 검사는 실제 offscreen QTest의 행2 클릭→Shift 행5 클릭→
Shift 방향키, 시험 A→B→A의 `%`/`kPa`와 `[4,17]` 복원, native 계수 셀 편집을 포함한다.
빈값/음수/문자/NaN/Infinity의 cold subprocess 재열기와 완료 후보가 있어도 invalid 계수를
채택하지 못하는 경로를 확인했다. 계수 수정 후 과거 후보 차단, Undo 새 분기와 재열기 뒤
번호 증가, 저장된 실행 중 문서의 종료/교체 확인창에서 계속 보기와 중단을 QTest로 검사했다.
후속 native 검사의 채택 가능 표시 불일치 보고에 대해, 버튼과 고정 표시가 같은 채택 조건
snapshot을 사용하도록 맞췄다. offscreen QTest로 채택 버튼→Yes 확인창을 조작한 직후와
이벤트 처리 뒤에 조건·버튼·고정 표시가 모두 채택 차단인지 확인하고 Undo/Redo와 계수
편집에서도 같은 일치를 검사했다. `09-adopted-target-1000x650.png`가 채택 후 위젯 렌더링이다.
이 회귀 검사만으로 native 화면 불일치의 원인을 확정하지 않는다.

재열기는 결과의 출발 원자료 hash, 열·단위·행 구간, 유효 입력 계수, 입력 snapshot hash와
보존 x/관측을 CSV 원바이트의 단위 환산·행 선택과 대조한다. solver/동정을 재실행하지 않는다.
위조된 hash/관측/입력 맥락을 거부해 현재 문서와 실행 중 타이머를 보존하는 회귀도 통과했다.
입력 snapshot hash는 로컬 저장 일관성 검사이며 서명이나 외부 신뢰 인증이 아니다.
앞선 잠정 결과 저장본에 새 입력 hash가 없으면 거부될 수 있다. 이 폴더의 `review.demo.json`은
새 검사에 맞게 다시 생성했다. 검사 보고서의 `source_sha256`이 검사한 세 파일을 식별한다.

`evidence/*.png`는 **QT_QPA_PLATFORM=offscreen에서 QWidget.grab()로 만든 위젯 렌더링**이다.
1440×900과 1000×650의 빈 상태·단위 오류·실패·비교 화면이며 OS 스크린샷이 아니다.
파일 대화상자는 테스트에서 경로 반환값을 대체한다. 종료/교체 확인창은 offscreen Qt 위젯에
QTest 입력을 전달한다. OS/브라우저 입력이나 실제 화면 조작은 하지 않는다.
오프스크린 Windows의 빈 글꼴 목록 때문에 설치된 Malgun Gothic을 명시적으로 등록한다.

Codex가 별도로 실제 Windows의 CSV/저장 chooser, 행 선택과 Shift 방향키, 채택·Undo/Redo,
dock Float/기본 배치 복구, 저장·종료·새 프로세스 재열기를 확인했다.
[독립 검토와 실제 조작 기록](../QT_REVIEW.md), [실제 재열기 캡처](../native-material-reopen.png)를
함께 읽는다. 도크 마우스 드래그·Shift 클릭·여러 DPI·보조기술·native 실패/취소는 미확인이다.
자동 검사는 동작 함수를 직접 호출하는 부분을 포함하며 전체 사용자 GUI 수용을 대신하지
않는다. 저장 후 Undo 이력은 복원하지 않는다. 10,000행 이하와 단일
증가 축/선형 데모 식만 지원한다. 여러 시험 동시 동정·holdout·법칙 선택·Plan 공유 owner·
제품 서비스·CLI/Python/MCP·실제 수치/물리 비교는 이 시제품의 범위 밖이다.
