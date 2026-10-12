# Pro D1의 실제 작업 경로 검토

2026-10-12. 실제 ChatGPT Pro 원고를 회수한 뒤 Codex, Astra/xhigh,
Sol/high가 각 책임 범위에서 확인했다. **현재 시제품의 사용성은 수용되지 않았다.**
사용자는 글이 과다하고 알아보기 어려우며 사용법을 추측해야 하는 화면을 지적했다.
현재 폼을 최종 제품 화면으로 사용하지 않는다. 화면 방향은 사용자 검토 전 제안이다.

## 사용자가 끝내지 못하는 경로와 교정

| 항목 | 관찰한 동작 | 필요한 변경 |
|---|---|---|
| Data 제외와 실행 입력 불일치 — P1 | A82 품질 제외 뒤 화면 train300/Data DIRTY인데 새 모의 run은 saved Data의301행과 A82를 포함 | 실행에 필요한 Data/Material/Plan의 buffer·dirty·정확한 참조를 검사하고 저장·명시 source 갱신 경로를 안내 |
| 다중 행과 곡선·명령 불일치 — P2 | Shift로78–85의8행을 선택해도 곡선 강조와 품질 제외는 마지막85 한 행 | 선택 범위를 표·곡선에서 공유하고 구간 전체 변경과 한 번의 Undo를 연결 |
| 편집기 키보드 이동 — P2 | 유효한0.87을 입력해도 Tab/Backtab이 편집기에서 벗어나지 못함 | 유효 입력 제출·다음/이전 셀 이동, invalid 입력의 진단·Esc 취소를 명시 구현 |
| MOO 채택 마지막 단계 부재 — P1 | p19 충돌 화면에는 취소·확인·제안 저장만 있고 CAD/Material Apply→각 저장이 없음 | p19를 유지한 owner별 준비·Apply·부분 저장·재시도·최종 receipt·재열기 전이를 추가 |
| SI stage의 다른 문맥 재열기 — P1 | 열 V-02/r4와 열탄성 V-03/r6 저장이 일반 V-03 implicit/explicit 화면으로 이동 | 각 정확 stage의 입력·단위·결과를 보존하는 저장·재열기·편집 복귀 |
| Material 참조 복구 문맥 — P2 | savedr19 참조 수리가 r17/currentr18 채택 충돌로 이동 | savedr19의 누락 파일 검사·동일 내용 위치 수리·changed-content 분기·취소를 연결 |
| 교정 원문의 다른 문서 열기 — P2 | CAL-018r2 원문이 Stiffness study 보고서와 Material fit으로 이동 | 정확 교정 원문·locator·유효 범위·누락 상태를 표시하는 viewer 연결 |
| 전체 Material 작업면의 정보 구조 | 설명·내부 상태·긴 버튼명, 아래로 밀린 주요 상태/조작, 큰 빈 공간과 곡선 제목 잘림 | 표·곡선 중심 배치, 작업명·단위·맥락별 옵션, 진단 분리, 지속적인 선택·저장·실행 상태, 도킹·resize·키보드·파일 작업 |

앞의 세 Qt 항목은 Sol/high가 기존 사용자 Python3.13/PySide6 6.9.1에서
QTest/순수 상태 검사로 재현했다. 이어지는 네 전이 항목은 Astra/xhigh가 실제
SCREEN_SPEC·PROTOTYPE_SCENARIOS·계약의 조작을 따라가 확인했다. 전체 SVG/JSON의
hotspot·시각 대조는 아직 해당 원본을 회수하지 못한 범위다.

Pro의 원래14개 상태 검사는 직접 재실행해 통과했다. 추가 사용자 경로에서 위 결함이
재현됐으므로 검사 통과를 전체 시제품 수용으로 해석하지 않는다. 부분 저장, 다른 client
충돌, Apply와 Save의 분리, invalid 원문과 recovery capsule의 보존도 제한적으로 확인했다.

## 화면 근거와 실제 실행의 경계

기존 Segoe UI를 명시 로드한 offscreen 렌더링에서1480×1040 창의 폼 높이는1383이며,
하단 mapped table과 채택·저장·복구 조작을 보려면 scroll이 필요하다. 시스템 폰트를
로드하지 않은 최초 offscreen 캡처의2962px 가로폭은 폰트 부재 영향이므로 결함 근거에서
제외했다. 정확 렌더링에서도 plot 제목 잘림과 정보 배치 문제는 보인다.

Windows native 새 프로세스의 Qt 창과 접근성 구조는 확인했다. 창 활성화가 두 번 실패했고
캡처가 검은 화면이어서 OS 입력을 중단했다. 이 실행을 실제 마우스·키보드·DPI 통과로
보고하지 않는다. 이전 별도 Material spike의 native 조작 근거는 [QT_REVIEW](QT_REVIEW.md)에
있으며 새 D1의 수용을 대신하지 않는다.

실제 재현 코드·JSON·검토 보고서는 로컬
`runs/pro-relay/20261012-desktop-design/pro-qt-review/`에 보존한다. source는 원 D1
`prototype/state_model.py`, `material_demo.py`, `material_demo.ui`이며 원본을 직접 수정하지 않았다.
Pro에게 실제 결함과 사용자 피드백을 전달해 기능·화면·Qt 소스의 교정을 요청했다.

## 유지할 설계 근거

독립 도구와 기존 Data/Material/PDE/Study/Evaluation·JobManager 소유를 재사용하며,
implicit/explicit/접촉/파괴/구성식/PDE/UQ/대리/MOO/원격·교정 요구를 삭제하지 않는다.
backlog의 참조와 선행 관계에서 추가 누락·순환은 발견되지 않았다.

Astra의 독립 합성 산술 확인에서 두 CSV의 전 행 변환, mask별 표본 수,
후보 objective/holdout, 접촉력·시각·gap, prescribed-F 응력·접선 fixture가 일치했다.
이는 합성 시안의 일관성 근거이며 제품 evaluator·solver·fit의 실제 실행 검증은 아니다.
기존 실패와 UNKNOWN/NOT_RELEASED는 유지한다.
