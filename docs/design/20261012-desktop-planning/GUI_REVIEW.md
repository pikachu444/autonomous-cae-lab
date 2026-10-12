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

## 최종 조작 교정과 설계 연결

`827ee9e`에서 root는 Pro의 집중 Qt 검사 6그룹과 UX04의 4개 경로를 실제로 실행했다.
그린 선→치수·구속→저장/재열기, saved pose45°/instances4/구멍/mesh1의 Simulation 전달,
선택 Hold 단계의 독립 편집, 현재 CAD draft와 다른 p19/p04 원 결과 형상,
방법별 합성 결과→Expert 사용자 reply→Study 판단과 일반 파일 재열기를 확인했다.
원 함수/수치 엔진이나 provider가 이 결과를 계산한 것은 아니다.

Astra/xhigh는 최종 원고·편집 화면·작업 흐름과 바뀐 조작을 독립 확인했다.
별도 검사에서 step 이름만 바꾸면 개별 time step/force가 삭제되는 문제와,
같은 DOE 결과 d1/d2의 근거가 발언별로 구분되지 않는 문제를 재현했다.
Luna/high는 기존 작업표의 원열/순서가 유지됨을 확인하고 공통 파일·보고서·장비와
GUI/CLI/Python/MCP 계약의 화면 연결이 불명확한 것을 찾았다.
Numerical의 UQ/Sobol/optimization 함수 번호 대응 오류도 Astra가 찾았다.

같은 Pro 작성자가 `049bbbc`에서 기능 두 문제를 교정했다. root가 실제 Qt 검사로
Hold 이름 변경 뒤 `2e-5`, `-125 N`, duration2 보존과 일반 저장→별도 프로세스→Qt
재열기를 확인했다. d1/d2 두 사용자 발언은 각 결과 ID와 선택 위치를 보존했고,
근거 열기로 정확한 행을 다시 선택했다. Astra도 앞선 독립 재현 순서로 두 문제의
해소를 확인했다. 이전 형식에 위치가 없는 모호한 근거는 임의로 복수 행을 붙이지 않고
Location not recorded로 남겼다.

Windows 상태 내보내기의 글꼴 누락과 Post A/B 값 잘림은 `af84968`에서 교정됐다.
기존 Segoe UI/Malgun Gothic을 현재 프로세스에 읽으며 폰트 파일을 복사·배포하지 않는다.
정상 글자와 첫 표시의 0.31/0.29mm 비교값을 실제로 확인했다.
root의 별도 Qt 조작 검사에서 1280×800 창 크기 변경, dock float 버튼의 분리·복귀,
View 메뉴 숨김·표시, 저장한 창 배치 재열기, Data 표/곡선 선택과 Ctrl+O의 Qt
파일 chooser를 확인했다. Windows OS 입력이나 화면 배율의 통과로 확대하지 않는다.

Pro `60a4fab`은 원74task의 기존열을 유지하며 Numerical의 task별 화면과 FN-01의 실제
파일 작업을 교정했다. 보고서·장비의 이전 텍스트 계약과 현재 미연결 시제품을 구별했다.
전체 화면 제출의 빈칸인 전용 report/측정 채널·신호 화면은 같은 Pro에 추가 작성하도록
요청했다. 그 산출물과 최종 연결 확인은 뒤의 기록에서 구별한다.

새 [작업 흐름 원본](pro-ux/Workflows.drawio)의 세 페이지를 draw.io Desktop32.4.1로
실제 export하고 열어 확인했다. 이 버전의 page index는1부터 시작하며, 처음0을 사용한
export 실패는 도면 결함이 아닌 CLI 인자 오류였다.

## 보고서·수집 교정과 최종 검토본

Pro `600f9f8`은 기존 Study/Data 소유를 재사용하는 전용 Report/Acquisition 창과 네 상태를
작성했다. Sol/high의 실제 Windows Qt 검사에서 절 편집·출력·일반 저장/cold reopen과
채널 Cancel·단위변환·표/곡선·부분입력·live 비활성화는 작동했다. 동시에 선택 .02s를
끝 .04s 값으로 바꾸는 오류와 편집된 절을 Use Study가 조용히 교체하는 문제가 발견됐다.
Astra/xhigh는 preview/source 불일치, 출력 참조 누락, 역사 F05를 현재 Study에 적용하는
문제와 작은 connection 표의 숨은 UNKNOWN을 찾았다. 같은 Pro에 재현을 전달했다.

`9e313e5`의 교정은 독립 Sol과 Astra의 실제 Windows Qt 재현에서 닫혔다.
Gauge 0/.02/.04s는 각각 0/.2294/.31mm, Contact pressure .02s는1.5MPa이며 Open source와
출력에 같은 field/time/association과 정확 참조가 남았다. 없는 .03s/field는 대체 없이
unavailable이며 기본 export를 막는다. 명시적 placeholder 출력은 누락을 표시한다.
Use Study Cancel은 전체 draft와 Undo를 유지했고 Replace 뒤 Undo도 원 내용을 복원했다.
일반 보고서 Save와 별도 Python 프로세스 재열기에서 내용과 원 결과 선택이 이어졌다.
Page preview와 선택 절이 동기화되고 현재 checks와 명시적으로 추가한 역사 F05가 구별됐다.
Acquisition의6행/UNKNOWN/ACK와 비활성 Connect/Start/Stop도 함께 보였다.

Pro `dd43015`은 supported gauge endpoints/Surface·measure row까지 원 Post 선택으로
복원하고 PDF overflow의 수정 페이지로 이동하도록 마무리했다. Sol의 한정 소스 검토에
추가 결함이 없었으며 root가 이 source의 Report/정확 선택/Acquisition 세 변경 경로를
Windows Python3.13.5/PySide6 6.9.1에서 실행했다. 출력·ordinary save·별도 프로세스·
cold Qt 재열기·미완성 수치 수정·선택·live guards가 통과했고 callback 오류는 없었다.
원 Pro 검사 helper는 offscreen 모달 종료 후 창 활성화를 누락하여 focusWidget=None을
delegate 누락으로 오인했다. 독립 Sol은 실제 delegate 생성과 창 활성화 후 입력 성공을
확인했다. root는 ignored 검사 사본에 activate/scroll만 추가해 위 검사를 수행했다.
Pro의 원격 환경 disconnect와 source-only 검토를 Windows 실행 PASS로 표시하지 않았다.

최종56상태 SVG/PNG는 Pro의 Qt/JSON 원본을 root가 Windows에서 렌더했다. 글꼴은 기존
Segoe UI/Malgun Gothic이며 파일을 배포하지 않는다. Report의 .02s 페이지와 표/곡선,
Acquisition 채널/종료 화면, 주요 CAD/Post/Numerical/Expert 화면을 실제로 열어 확인했다.
PDF의 .2294mm/.02s 페이지를 bundled Poppler로 렌더해 표·글자·출처가 잘리지 않음을
확인했다. Workflows.drawio의 네 페이지도 실제 draw.io Desktop export로 확인했다.
보고서/수집 페이지의 겹친 화살표 글자와 box를 통과한 복귀 선은 root가 배치만 교정하고
다시 export해 확인했다. 작업 의미·도구 소유권은 변경하지 않았다.
소스와 JSON은 편집 원본이고 SVG는 같은 view의 벡터 내보내기다. OS 창틀 캡처가 아니다.

재현 자료는 `report-acquisition-sol/correction-9e/`,
`astra-report-acquisition/correction-9e/`, `complete-final/`, `final-preview/`, `pdf-final/`,
`flow-preview/`에 남는다. 독립 검토의 원고·실행 역할과 bounded 범위는 각 보고서에 있다.

## 실제 Windows 확인의 한계

Qt offscreen 렌더와 QTest 입력·chooser·새 ReviewSession/창의 재열기 근거다.
새 native 창은 열렸으나 Windows 화면 제어의 검은 캡처와 활성화 실패로 직접 입력을
중단했다. 최신 `049bbbc`의 별도 실제 CAD 창도 프로세스/창 제목은 확인됐지만 캡처는
검은 화면·접근성 텍스트 없음이었다. 잠금/PIN 상태라고 추정하거나 실패한 좌표 입력을
반복하지 않았다. native 마우스·도킹·실제 DPI·OS 파일 chooser 수용을 주장하지 않는다.
최종 `dd43015`도 별도 `Clamp design — CAD / FE` Windows 창으로 실행하고 제목을
확인했다. 동일 제어 도구의 캡처는 여전히 검은 화면/접근성 없음이어서 직접 입력 검증을
확대하지 않았다. 앞선 창의 사용자 draft는 닫거나 지우지 않았다.
이전 Material spike의 native 근거를 새 전체 GUI의 통과로 옮기지 않는다.

로컬 재현 원본은 ignored `runs/pro-relay/20261012-desktop-design/` 아래에 있다.
`ux-review/`와 `ux-review/correction-3c80/`의 스크립트·JSON·보고서,
`astra-ux-review.md`, `ux-visual/`의 실제 창 렌더와 `ux-vector/`의 Qt SVG export다.
검사한 소스별 근거를 구별하며 이후 수정본에 소급 적용하지 않는다.
추가 근거는 `followup-827/`, `ux04-827/`, `ux06-049/`, `desktop-controls/`와
`astra-final-review.md`, `astra-final/correction-049/review.md`, `map-final-review.md`다.
Pro의 원격 Linux 검사 보고와 Codex의 Windows interpreter 실행은 서로 다른 근거다.

현행 수용 상태와 다음 행동은 [CURRENT_STATE](../../../CURRENT_STATE.md)에만 둔다.
[전체 기능/구현 명세](pro-authored/FUNCTION_SPEC.md)와
[실행 가능한 새 Qt 원본](pro-ux/README.md)을 함께 검토한다.
