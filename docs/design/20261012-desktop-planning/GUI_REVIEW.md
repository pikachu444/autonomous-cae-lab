# 전체 도구 Qt 시안의 실제 검토

이 기록은 새 실제 Pro 대화의 `pro-ux/` 원고에 대한 Codex 통합 검토다.
Windows의 기존 Python3.13·PySide6 6.9.1을 사용했고, 계산·native host 그림은 합성이다.
제품 본구현·solver/optimizer/provider 실행·공학 승인으로 해석하지 않는다.

## 처음 받은 화면과 필요한 교정

Pro의 `3ab34b0`에서 CAD/FE, Simulation, Runner, Post, Numerical, Expert, Study와
Data/Material/PDE/Evaluation/선택 Workbench의 창을 실제 Qt로 렌더링했다.
Sol/high는 실제 입력·대화상자·키보드 조작을, Astra/xhigh는 같은 원본 요구와 전체
화면·핵심 작업을 독립 검토했다. 두 검토자는 원고를 수정하지 않았다.

CAD의 스케치·조립·메시·조건 선택과 Simulation의 트리가 해당 작업 편집으로 이어지지
않았고, 폭 변경도 뷰를 바꾸지 않았다. Post 필터·측정·비교는 조작 대상이 부족했고,
최적화 방법별 대상과 결과가 같은 MOO 예제로 남았다. 지배되는 후보가 Pareto front에
포함됐다. Expert/Workbench의 논점 이름은 Qt 텍스트 객체가 사라져 표시되지 않았다.
Expert의 새 Numerical 계획은 빈 변수·응답을 채울 조작이 없었다.

필수 해석 값·빈 접촉면·오래된 메시의 실행 전 검사, Post 필드/단위 Undo와 시간별 값,
Numerical Undo 후 표·입력 불일치도 실제 Qt에서 재현했다. Pro에게 UX-FIX-01/02로
정확한 조작·화면·수정안을 전달했고 실제 사용자 메시지에서 전송을 확인했다.

## 교정 소스에서 확인한 동작

Pro의 `3c80e1d`에서 CAD 생성·조건 Tasks, Numerical 평가기·변수·응답 편집과
시간별 Post 표시가 추가됐다. 전체 창을 다시 열고 논점 지도 글자 표시를 확인했다.
Sol/high의 제한된 실제 Qt 조작에서 다음 경로가 작동했다.

- 필수 값 오류 → 실행 차단 → 해당 편집 위치 → 수정·저장 → 합성 검토 attempt.
- Expert 계획 → 평가기 선택·변수/응답 정의 → 저장·합성 attempt → 새 창 재열기.
- Post 필드 선택의 한 단계 Undo/Redo, time0의 값·곡선 커서, 없는 배열/association의 unavailable.
- Numerical Ctrl+Z/Y 뒤 표와 저장할 값의 일치.

작은 시간 증분의 실제 입력은 새 문제로 남았다. Qt 기본 float 편집기가 `1e-6`을
`0.00`으로 열고, `0.001` 입력을 Enter·저장 후 `0.0`으로 바꿨다. 정상 attempt 경로의
교정 검사는 `1.0`으로 수행한 것이며 이 precision 문제를 해결한 검사가 아니다.
Numerical의 평가기 한 행이 큰 빈 공간을 차지하는 배치도 실제 렌더에서 확인했다.
UX-FIX-03으로 Pro에게 정밀도·지수 입력, 배치와 무료 Expert 역할/모델 선택을 전달했다.

`48cbac3`에서는 root가 Pro의 Qt 검사를 실제 Windows Python에서 실행했고,
Sol/high가 지수 입력·부분 입력·Undo/Redo·저장/재열기를 독립 확인했다. `1e` 초안은
보존하면서 실행을 차단하고 `2e-6`으로 고치면 정확한 합성 입력이 생성됐다.
상단 평가기 행은31px로 렌더됐다. Astra는 기본 CAD·메시·Post 선택/측정·Pareto와
Expert 역할/모델 설정의 교정을 확인했지만 스케치 선 삭제, 저장한 자세·instance·
비교 형상, selected step, inverse train/holdout과 방법별 결과→후속 토론을 남겼다.
같은 실제 Pro 작성 task에 UX-FIX-04를 공식 도구로 전달해 수신 본문을 확인했다.

`b46b8ba`를 회수한 뒤 root의 Qt 입력 검사에서 앞선 교정의 회귀는 없었다.
별도 전체 연결 검사에서 CAD 폭84 편집·메시 수정·저장→같은 모델을 Simulation에
선택→합성 attempt/보존 결과→Post의 정확한 결과 열기→MOO p19의 CAD/Material
개별 Apply/Save→저장한 후보 선택→새 ReviewSession/창의 재열기가 작동했다.
Material 저장 실패의 시나리오에서는 이미 저장한 CAD를 유지하고 Material만 재시도한
뒤 같은 후보 선택을 완료했다. 실패 주입 조작은 정상 채택 대화상자에서 Review로 옮겨졌다.
폭84는 후보 두께13.7 적용 뒤에도 유지됐고 과거 실행 결과와 사용자 답글이 이어졌다.
Simulation 저장은 이 검사에서 owner 명령을 사용했다. CAD chooser는 Qt offscreen이며
OS 파일 chooser 검증으로 표시하지 않는다. Numerical 방법별 결과와 신규 교정의
후속 검토는 이 연결 성공으로 대체하지 않는다.

## 확인 범위와 재현 자료

Qt offscreen 렌더와 QTest 입력·chooser·새 ReviewSession/창의 재열기 근거다.
새 native 창은 열렸으나 Windows 화면 제어의 검은 캡처와 활성화 실패로 직접 입력을
중단했다. 마우스·도킹·실제 DPI·OS 파일 chooser 수용을 주장하지 않는다.
이전 Material spike의 native 근거를 새 전체 GUI의 통과로 옮기지 않는다.

로컬 재현 원본은 ignored `runs/pro-relay/20261012-desktop-design/` 아래에 있다.
`ux-review/`와 `ux-review/correction-3c80/`의 스크립트·JSON·보고서,
`astra-ux-review.md`, `ux-visual/`의 실제 창 렌더와 `ux-vector/`의 Qt SVG export다.
검사한 소스별 근거를 구별하며 이후 수정본에 소급 적용하지 않는다.

현행 수용 상태와 다음 행동은 [CURRENT_STATE](../../../CURRENT_STATE.md)에만 둔다.
[전체 기능/구현 명세](pro-authored/FUNCTION_SPEC.md)와
[실행 가능한 새 Qt 원본](pro-ux/README.md)을 함께 검토한다.
