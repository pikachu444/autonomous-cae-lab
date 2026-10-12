# Material 시제품 교정과 실제 창 확인

2026-10-12. 기존 Pro v2에서 만든 **기획용 Qt 기술 시제품**에 대한 기록이다.
전체 새 Pro 설계·제품 구현·물리 수용의 판정은 아니다. 파일/실행 방법은
[시제품 README](qt_prototype/README.md)를 따른다. 실제 Windows 확인은 computer-use
스킬의 창별 입력 API로 수행했으며 인증 화면은 조작하지 않았다.

## Astra 독립 교정 검토

실제 `gpt-6-astra/xhigh` 읽기 전용 검토가 다음 결함을 재현했다. Sol/high 작성자가
시제품 폴더만 교정하고 Astra가 관련 코드·QTest·위젯 렌더링을 재검토했다.

| 원 지적 | 교정과 확인 |
|---|---|
| Shift 선택 중 기준 셀 소실 | 같은 자료에서 표 재생성 방지. 독립 QTest 클릭→Shift 클릭 `[2,5]`, 방향키 `[2,6]` 확인 |
| 시험 A→B→A에서 단위/구간 초기화 | 시험별 mapping/selection 보존. `%/kPa`, `[4,17]` 및 B `[3,10]` 저장·재열기 확인 |
| invalid E를 이전 유효값으로 되돌려 실행 허용 | 빈값/문자/음수/비유한 원문 초안 보존, 실행·채택 차단. 별도 프로세스 재열기에서 계산 0회 확인 |
| 계수 수정 뒤 과거 후보 채택 가능 | 원자료·매핑·구간·출발 계수가 같아야 채택. 수정 후 차단, Undo 복원 후 허용 |
| 변조된 원자료/관측값 저장본 허용 | source/input hash와 원자료에서 재구성한 관측 대조. hash 재계산한 관측 변조도 거부, 현재 문서·실행·timer 보존 |
| 좁은 창에서 채택 대상/실패 상태 숨김 | 고정 후보 번호·상태와 현재 입력 준비 상태 분리. 1000×650 실패/invalid/후보 렌더링 확인 |
| 저장한 실행 중 문서의 종료/교체 경고 누락 | 저장 여부와 별개로 local DEMO 중단/계속 보기 경고. 한정 QTest 확인 |
| Undo 분기에서 다른 입력에 같은 편집 번호 재사용 | 별도 저장되는 증가 serial. Undo 분기 및 재열기 뒤 새 편집 증가 확인 |

Astra는 이 시제품 범위에서 원 P1/P2 지적이 해소됐고 새 P1/P2를 찾지 못했다고
보고했다. 최초 재검토의 main hash는 `6d3dc977…`였다. 실제 창의 최초 채택 직후
캡처에는 고정 후보 표시와 disabled 버튼/하단 진단이 잠시 일치하지 않았다.
뒤 Undo/Redo에서는 일치했다. 원인은 확정하지 않았다. 표시와 버튼이 하나의
`adopt_ready` 값을 공유하도록 교정했고, QTest 버튼→Yes 직후/이벤트 처리 후·
Undo/Redo/계수 편집 검사와 [교정 렌더링](qt_prototype/evidence/09-adopted-target-1000x650.png)을
Astra가 추가로 읽어 기존 판정을 유지했다. 이 추가 검토에서는 검사를 재실행하지 않았다.

최종 교정 소스:

- main.py SHA256 `bc5e52bf7440c46ed8e55bfcad41dd2d6441472b04848f474ed5d631ea03f653`
- selfcheck.py SHA256 `48e6b22826ef40b6de129cf2128a7b8b96373296e006f9abb8873208ad144849`
- material.ui SHA256 `9bd83a4b72b7019050d6a72023d710ccbad43897a9df474f8b651099a0852228`

## Codex 실제 Windows 조작

사용자가 잠금을 해제한 뒤 새 창 상태를 관찰해 다음 경로를 수행했다.

| 실제 조작 | 관찰 결과 |
|---|---|
| Designer 원본 열람, 열린 표 편집 모달 Escape | material.ui의 실제 편집 창 확인. 원본 변경 없음 |
| 시제품 Ctrl+I → native 파일 chooser → demo_test.csv → Enter | 21행 표와 관측 곡선, 열 역할/단위 표시, dirty 상태 |
| 원 행2 선택 → Shift+↓ 두 번 | 2–3행은 최소3행 오류·실행 차단. 2–4행은 같은 곡선 구간 강조·실행 허용 |
| DEMO 시작 → 완료 → 후보 채택 → Yes | 후보 #1의 원 입력 보존. E `1→2.4 MPa`, b `0→0.02 MPa`와 DEMO 안내. 실제 동정 아님 |
| Ctrl+Z / Ctrl+Shift+Z | 계수 복원/재채택, 기존 후보/곡선 유지. 원 후보 입력과 현재 입력이 다르면 채택 차단 |
| dock Float → 창 메뉴 기본 배치 복원 | 실제 floating 패널과 원 위치 복구. 마우스 drag 경로는 미확인 |
| Ctrl+S → native 저장 chooser → 새 로컬 경로 | 저장됨 표시와 파일 생성. 구간 `[2,4]`, 계수 E2.4/b0.02, 후보1개·원 입력 유지 |
| Alt+F4 → 새 pythonw 프로세스로 저장본 열기 | 이전 창 ID `18091456`이 사라지고 새 ID `5574768`, PID83340·20:05:37 KST 시작. 저장 상태·구간·계수·이전 후보/잔차 복원 |

실제 저장본은 ignored `runs/pro-relay/20261012-desktop-design/native-material.demo.json`에
있다. 종료 뒤 최종 교정 소스를 새 프로세스에서 읽었다. 재열기 화면의 고정 후보
‘채택 차단’, disabled 버튼과 원 입력 불일치 진단이 일치한다.
[실제 Windows 재열기 캡처](native-material-reopen.png)는 공개 합성 자료만 담은 창이다.
관찰한 창 캡처는 1443×932이며 여러 DPI 배율 수용을 뜻하지 않는다.

## 남은 확인

전체 새 Pro 화면과의 일치·다중 시험/holdout/법칙·제품 owner/서비스·CLI/Python/MCP·
실제 optimizer/solver는 이 시제품에서 확인하지 않았다. 현재 시안의 계산은 고정 계수와
Qt timer이고, 작은 DEMO RMSE는 공학 검증이 아니다. actual mouse drag/Shift-click,
좁은 창의 OS 조작, 여러 DPI/접근성·대용량과 native 실패/취소는 추가 확인 대상이다.
현재 보고서의 offscreen/QTest 통과와 실제 창에서 조작한 위 경로는 서로 다른 근거다.

입력 hash가 없는 과거 잠정 시제품 저장본은 강화한 검사에서 거부될 수 있다.
제품 저장 형식의 migration이나 product release 결정으로 확대하지 않는다.
