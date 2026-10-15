# 원자료 복귀의 Windows 확인 범위

2026-10-15. 실제 Pro의 A2와 native C1을 통합하고, Sol의 화면·자동 차트 열 충돌 교정과
Codex의 명령 전달·창 수명 연결을 적용했다. 전체 후처리 완료나 공학적 승인은 아니다.

Windows Qt에서 원 A/B·보간 B 양끝 행과 원축/공통축 단위, 파일 선택 취소, 늦은 응답
차단을 확인했다. 실제 broker의 submit→owner dispatch→완료 조회 왕복은 별도 작은
검사로 확인했다. 내부 예약 인수와 원행 인수를 구분하고, 기존 보고서 읽기 명령의
허용 목록과 닫힌 창의 활성화 callback도 교정했다. 물리·행 대응 대역과 실제 전송 경계를
구분하며 새 해석은 실행하지 않았다.

ParaView 6.2의 실제 pvpython에서 native C1 전용 검사 79개가 통과했다. VTK는 실제지만
이 검사의 chart property/domain/owner는 대역이다. 별도 공개 VTU 기술 확인에서는 실제
중첩 Group Datasets→XY chart로 지정 leaf·flat ID·응답/축 벡터 성분을 선택하고,
Assembly/BlockSelectors/domain·표시 속성 재읽기·AppendSelections를 확인했다.
이 한 차트 확인을 전체 저장 비교의 복귀·OS 창 활성화 성공으로 확대하지 않는다.

Astra가 자동 추가되는 좌표 열·vtkOriginalIndices와 원 응답/축의 동명 충돌을 발견했다.
Sol은 선택한 배열의 원명과 native 성분명이 자동 열에 덮이는 경우만 거절하도록
교정했다. 미선택 원 배열은 유지한다. 새 충돌·정상 대조 6개만 추가로 확인했고 앞선
79개와 native scene을 반복하지 않았다. Astra가 최종 소스와 이 국소 결과를 재검토했다.
Pro 원본과 Sol 국소 작성은 로컬 기록에서 구분한다.

로컬 실행 자료는 `_workspace/delivery-post/origin-return-a2-windows/`,
`origin-return-a2-broker-check/`, `origin-return-a2/root-bridge-lifecycle/`,
`origin-return-c1-windows/`에 있다. 실제 창 확인은 Qt 이벤트로 수행했다.
모든 실행의 소유 reader·서비스·Windows Job을 정리했다.

Windows OS foreground/키보드, 전체 저장 곡선→원 native owner→저장·앱 종료·새 GUI 복귀,
분산 데이터의 행 대응, 전체 FN27/FN28과 ParaView File→Exit 수용은 아직 완료가 아니다.
실제 계보가 없는 Data에는 원 측정 버튼을 만들지 않으며 보존 Data 읽기와 native 복귀
실패는 독립적으로 표시한다. 해시·성분·단위·owner·현재 편집 보호를 우회하지 않는다.
