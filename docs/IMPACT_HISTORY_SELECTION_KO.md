# 충격 해석 이력 선택

저장한 Simulation의 결과를 골라 접촉쌍, 부호 있는 성분, 실제 표본의 시작과 끝을
선택한다. 이 선택과 표본 적분은 보존 응답을 읽는 작업이다. 솔버나 변환기를 다시
실행하지 않으며 원 결과를 수정하지 않는다.

## 물리량 구분

| 이력 | 의미와 단위 |
|---|---|
| 원 접촉쌍 누적 충격량 | 원 TH의 부호 있는 누적값 [N s] |
| 접촉쌍 구간 평균 힘 | 실제 표본 구간의 `(J_b-J_a)/(t_b-t_a)` [N]. 순간 힘이나 물체별 반력이 아니다. |
| 힘 표본 사다리꼴 적분 | 선택한 평균 힘 표본을 적분한 별도 파생값 [N s]. 선택 시작을 0으로 정하며 원 누적 충격량과 같다고 가정하지 않는다. |
| 현재 총질량·추가 질량 | 각 원 출력 채널을 구별한다. 입력 기반 초기 질량은 별도 항목이며 두 채널의 차로 만들지 않는다. |
| 요소 내부 에너지 밀도·전체 내부 에너지 | 서로 다른 위치·물리량이다. 밀도를 전체 에너지로 표시하지 않는다. |
| 대응면 분리 거리 | 초기 대응 절점으로 구한 파생 거리 [mm]. 솔버의 native PENE 관측이 아니다. |

원 TH의 누적 충격량 [N s]에서 힘 [N]을 구하는 것은 단위 배율 변환이 아니다.
각 평균 힘 표본이 사용하는 실제 시간 구간과 원행을 함께 보존한다. 가운데 표본의
평균 구간은 선택한 시작 또는 끝 밖을 포함할 수 있다. 이 경우에도 구간을 잘라
새 값을 만들지 않는다.

표면 이름과 원 방향 근거를 표시하며 native 부호를 유지한다. 선택한 물체의 반대
부호 반력이나 기록되지 않은 side별 힘을 추정하지 않는다. 개별 에너지·일 이력은
에너지 평형 판정을 대신하지 않는다. 기존 에너지 급증과 원 실패·UNKNOWN도 남긴다.

## 표본과 선택 보존

시작과 끝은 원 응답에 있는 정확한 시각이어야 한다. 요청 종료 시각으로 마지막
표본을 연장하거나 가장 가까운 표본으로 바꾸지 않는다. 원 TH의 레코드 순번,
animation 프레임 순번, CSV 실제 행은 서로 구별한다. 품질·계산 포함·끊김 마스크를
원값과 함께 보존한다. 누락을 0으로 채우거나 끊긴 구간을 선 또는 적분으로 잇지 않는다.

표본 적분을 명시하면 선택 시작의 0은 적분 기준일 뿐 측정값이 아니다. 누락·제외·원행
끊김 뒤에는 적분을 다시 0에서 시작하지 않는다. 중복·역순·비유한 시각과 실제 표본이
아닌 끝점은 거절한다.

저장 신원에는 원 문서·job·입력 개정과 해시·원 결과 해시, 선택 응답, 실제 시각·원행·마스크,
파생량 선택과 선택 내용 해시가 포함된다. 선택은 원 결과를 교체하는 결과가 아니다.
Study나 수치 계획에 전달할 때도 원 결과와 이 선택의 관계를 유지해야 한다.

## Simulation에서 Study와 계획으로 전달

저장한 Simulation에서 보존 결과를 선택하고 **연구 → 충격 이력 선택…**을 연다.
채널·실제 시작/끝 표본과 원값 또는 표본 적분을 고른다. 곡선과 표에서 원행,
계산 포함 여부, 평균 힘의 실제 지지 구간을 확인한다. 이 창의 읽기 성공과
원 계산의 완료·실패·취소 상태를 구별하며 새 솔버 실행은 없다.

**Study로 전달**은 같은 원 결과와 선택 내용 해시를 증거에 보존한다. Study의
‘결과 읽기’는 그 선택의 단위·표본·누락 구간을 표시한다. 원 결과의 다른 채널로
선택을 넓히지 않으며 누락 표본 사이를 선으로 잇지 않는다. 예를 들어 평균 힘의
표본 적분을 선택했다면 단위는 원 평균 힘의 N이 아닌 N s다.

**수치 계획으로 전달**은 먼저 같은 선택을 Study에 저장한 뒤 그 Study의 정확한
저장 개정을 원본으로 Numerical 계획을 연다. 계산 방법·대상 backend는 사용자가
지정해야 하며 자동 계산은 시작하지 않는다. 전달 직전 다른 창이 Study의 증거를
바꾸면 원 편집을 보존하고 충돌을 알린다. 바뀐 증거를 덮어쓰거나 다른 선택으로
계획을 만들지 않는다. 저장 후 별도 프로세스에서도 같은 Study 곡선과 Plan의
원 Study/선택 관계를 읽을 수 있다.

## Python에서 읽기

기존 Workbench owner가 검증한 저장 결과를 사용한다. 아래 `document_id`와 `job_id`에는
실제 저장 결과를 지정한다. `response_name`은 `history_catalog`의 기존 채널 이름이다.

```python
from caelab.workbench import Workbench
from caelab.impact_responses import history_catalog, select_history

wb = Workbench("saved-workspace", configuration={"workers": 1})
try:
    document = wb.document_open(kind="simulation", document_id=document_id)
    result = wb.document_result(document["id"], job_id)
    snapshot = {
        "source": wb.document_result_reference(document["id"], job_id),
        "result": result,
    }
    channels = history_catalog(snapshot)["channels"]
    times = result["responses"][response_name]["raw_samples"]["transformed_axis"]
    selected = select_history(snapshot, {
        "response": response_name,
        "start_s": times[10], "end_s": times[30],
        "side": "native", "transform": "identity",
    })
finally:
    wb.shutdown()
```

`transform="sample_trapezoid"`는 구간 평균 힘 [N]에서만 허용한다. 함수는 파일을 읽거나
명령을 제출하지 않는다. 원 결과의 읽기·검증·저장과 Study·Plan 수신은 기존 owner가 담당한다.

## 확인 범위와 한계

전용 검사는 정확한 끝점·원행·마스크·평균 구간, 원 충격량과 표본 적분 구분, 누락 뒤
적분 중단, 중복·비단조 시각 거절, 질량·에너지 구분과 원 실패 보존을 확인한다.
기존 18개 접촉쌍 응답×150표본과 L03 P1 저장 결과를 재사용하며 새 native 계산은 없다.
실제 Simulation 창에서 두 결과의 선택→Study→미실행 Plan→저장·별도 cold 수신을
확인했다. 150표본 사례의 선택은 원행40–60의21표본이며 P1 선택은50표본이다.
선택 응답의 N s 단위와 저장 Study의 결과 재읽기를 일반·좁은 창에서 확인했다.
별도 통제 Qt 표시 검사에서는 `[1, None, -2]`의 두 유효점 사이를 끊는 것을 확인했다.
통제 fixture를 실제 native 결과나 저장 owner 실행으로 세지 않는다. 마지막 두 표시
교정은 같은 독립 검토자가 원 참조·값·Job 불변과 실제 화면 근거로 폐쇄했다.

원 external workspace 접근과 native reader·변환기·솔버를 차단한 새 프로세스에서도
보존 응답을 읽는다. 복사된 saved revision의 보존 artifact 해시 검증은 기존 owner 규칙대로
수행한다. 보존 파일까지 없어진 상황의 무결성 검사를 생략하는 기능은 아니다.

CSV converter의 source는 `NOT_PROVEN_BY_RELEASE`를 유지한다. raw TH 경로는 converter를
우회한 기존 reader이며, 고정 solver producer source와 converter source를 같은 것으로
표시하지 않는다. 읽기 성공, 원 솔버 종료, 수치 타당성, 공학 적합성은 별개의 상태다.
