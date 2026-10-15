# 처리된 Data를 기존 Plan에 추가

Data 창은 기존 Plan의 NumericalWindow를 열고 `can_stage_processed_trial()`이 참일 때 `stage_processed_trial(source, result)`를 호출한다. 준비 조건은 Plan 읽기 완료, fit 모드, 유효한 재료, 진행 중 요청/채택 없음, 충돌 없음이다. 원래 로컬 편집은 보존한다.

`source`에는 원 Data의 `document_id/job_id/input_revision/input_sha256` 및 `processing_revision`을 넣는다. `result`는 실제 `data.processing.result`의 보존 결과다. 처리 기록의 원본 입력과 차수를 확인한 뒤 기존 ExperimentDialog로 응답/측정 변형/조건/용도/가중치를 검토한다. 수락하면 로컬 시험 초안만 추가한다. 소유자 적용, 정책 채택, 저장, 새 처리/계산은 실행하지 않는다. 취소/다른 Plan으로 전환/세대 변경 때 추가하지 않는다. 반환값은 추가 성공 여부다.

저장된 처리 시험 읽기는 `data.processing.result`에 정확한 처리 차수와 응답/측정 driver의 문자열 목록 `selection`을 보낸다. 원 import로 대체하지 않는다. 캐시는 원 입력 네 항목과 처리 차수, 선택 채널을 구별한다. 전체 처리 상태가 부분 실패여도 Core가 명시 선택한 응답 읽기를 성공으로 반환한 범위만 읽으며 전체 처리 성공으로 바꾸지 않는다.

기존 `experiment.selection.sample_policy`는 표 편집/조건 편집에서 그대로 보존한다. 선택 시험의 구간 채택 여부를 표시하고, 구간이 연결된 시험의 응답 변경은 새 시험 추가로 안내한다. 새 정책을 계산하거나 이전 응답의 정책을 다른 응답에 적용하지 않는다. 선택 표본 정책 검토/명시 채택은 Data 담당의 SamplePolicyDialog와 기존 Core 명령을 연결하는 다음 묶음이다.

GUI 대역 검사 4개: 미확정 값/소유자/호출자 입력 보존, 잘못된 원본과 늦은 세대 거절, 정확 처리 차수/채널 읽기, 구간 정책 무손실. 실제 Data C1 owner가 내보낸 공개 결과를 Windows 창에서 정상/좁은 크기로 읽고 포커스/Esc/정책 보존을 확인한다. 계산이나 정책 채택 완료를 이 GUI 검사로 주장하지 않는다. Data C2의 canonical fit consumer 및 공통 입력 스키마는 root/실제 Pro 소유다.
