# 관측 표본 정책 검토 화면 API

`apps.research.data_sample_policy_dialog.SamplePolicyDialog(proposal, channel, parent=None)`은
실제 Core의 `data.sample_policy.preview` 결과와 해당 전체 processing channel을 받는다.
둘의 frozen domain/sample ID가 다르면 표시하지 않는다. 입력은 deepcopy하며, 표본의 포함·피팅/
검증 역할·가중치만 `.entries`에 편집한다. `exec()==Accepted` 뒤에 호스트가 별도의 명시적
`data.sample_policy.adopt`를 호출한다. 이 대화상자는 요청·저장·계산·소유자 변경을 수행하지 않는다.

표의 품질/계산/처리 제외는 읽기 전용이다. 선택한 표본의 실제 원본 열·행·값·기여 계수는 기존
`trace_sample`로 읽으며 새 계수를 계산하지 않는다. 원행 번호를 파생 표본 ID로 대체하지 않는다.
대량 자료는 처음 표본을 바꾸어 최대1000개씩 표시하고 보이지 않는 표본의 기존 정책은 보존한다.
일괄 용도/가중치 편집은 선택을 유지한다. `1e`/빈값/음수 가중치는 원문을 남기고 채택을 막는다.

Numerical GUI는 현재 owner의 선택한 trial에서 이 창을 사용한다. 미적용 Plan 초안이나 충돌이
있으면 기존 owner 적용 경계를 먼저 확인하고, 검토한 base/command ID와 entries로 adoption을
수행한다. late acknowledgement가 새 입력을 지우지 않도록 호스트의 기존 보호를 유지한다.
이 UI를 열거나 Accepted를 받는 것이 이미 채택되었거나 독립성 검사를 통과했다는 뜻은 아니다.

2026-10-15 canonical C1 처리 엔진의 공개 CSV fixture로3개 단위 검사를 수행했다. 실제 Windows
보통/좁은 창에서 실제 raw 기여 계수, 선택 유지, invalid1e 보존을 확인했고 native_check가 실행한
창은 종료했다. 서비스 adoption/fit/cold reopen의 전체 동선은 Numerical 연결과 C2 통합 뒤에
별도로 확인한다. 현재 main의 C01/derived fit 완료 주장을 추가하지 않는다.
