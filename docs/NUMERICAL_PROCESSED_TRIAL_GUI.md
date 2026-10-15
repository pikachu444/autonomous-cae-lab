# 처리된 Data를 기존 Plan에 추가

Data 창은 기존 Plan의 NumericalWindow를 열고 `can_stage_processed_trial()`이 참일 때 `stage_processed_trial(source, result)`를 호출한다. 준비 조건은 Plan 읽기 완료, fit 모드, 유효한 재료, 진행 중 요청/채택 없음, 충돌 없음이다. 원래 로컬 편집은 보존한다.

`processed_trial_stage_pending()`은 읽기 응답을 기다릴 수 있는 동안만 참이다. Data host는 임의의 15초 제한 대신 이 공개 상태와 준비 여부를 확인한다. 읽기 실패, 닫힌 창, 충돌, 불확인 채택은 기다림을 끝내며 원래 오류를 보존한다. 소유자 쓰기 요청을 읽기 대기로 취급하지 않는다.

`source`에는 원 Data의 `document_id/job_id/input_revision/input_sha256` 및 `processing_revision`을 넣는다. `result`는 실제 `data.processing.result`의 보존 결과다. 처리 기록의 원본 입력과 차수를 확인한 뒤 기존 ExperimentDialog로 응답/측정 변형/조건/용도/가중치를 검토한다. 수락하면 로컬 시험 초안만 추가한다. 소유자 적용, 정책 채택, 저장, 새 처리/계산은 실행하지 않는다. 취소/다른 Plan으로 전환/세대 변경 때 추가하지 않는다. 반환값은 추가 성공 여부다.

저장된 처리 시험 읽기는 `data.processing.result`에 정확한 처리 차수와 응답/측정 driver의 문자열 목록 `selection`을 보낸다. 원 import로 대체하지 않는다. 캐시는 원 입력 네 항목과 처리 차수, 선택 채널을 구별한다. 전체 처리 상태가 부분 실패여도 Core가 명시 선택한 응답 읽기를 성공으로 반환한 범위만 읽으며 전체 처리 성공으로 바꾸지 않는다.

전체 보존 결과가 부분 실패인 경우도 같은 시험 조건 창에서 응력과 측정 변형 채널을 검토할 수 있다. `선택 채널 확인`은 그 두 채널(지정 변형구배를 쓰면 응력 하나)만 기존 Data 서비스에 다시 조회한다. 같은 원본 입력/처리 기록/결과 바이트의 선택된 응답이 원 화면과 일치하고 Core가 해당 범위의 성공을 확인해야 수락한다. 전체 조회로 재시도하거나 실패 채널을 만들지 않는다. 검토 중 계획이 바뀌거나 조회에 실패하면 시험을 추가하지 않는다. 취소하면 미확정 입력과 원 결과를 보존하고 늦은 응답을 사용하지 않는다. Data의 `ExperimentDialog(selected_result_reader=...)` 및 host 읽기 대기 변경과 함께 통합한다.

기존 `experiment.selection.sample_policy`는 표 편집/조건 편집에서 그대로 보존한다. 선택 시험의 구간 채택 여부를 표시하고, 구간이 연결된 시험의 응답 변경은 새 시험 추가로 안내한다. 새 정책을 계산하거나 이전 응답의 정책을 다른 응답에 적용하지 않는다.

선택한 처리 시험의 `표본 용도…`는 계획 적용 후 활성화된다. Data의 실제 `data.sample_policy.preview` 결과와 전체 frozen channel을 Data 담당 SamplePolicyDialog에서 검토한다. 수락하면 기존 Numerical 적용 결과 확인 transport를 재사용하여 `data.sample_policy.adopt`를 명시 한 번 호출한다. 자동 저장/계산은 하지 않는다. 응답 유실 때 같은 명령/입력/세대를 다시 확인하며, 불확인 중 실행/적용을 막는다. 늦은 성공 응답은 이후 편집을 덮지 않고 충돌 상태로 보존한다. 창을 닫았다면 다시 열어 현재 소유자의 표본 용도를 확인해야 한다.

이미 채택된 표본 정책을 다시 열 때 Core의 `validate_sample_policy`와 동일 frozen domain을 확인하고, 정확한 sample ID별 기존 포함/역할/가중치를 Data 대화상자의 `initial_entries`로 넣는다. 새 preview의 기본 피팅 용도로 초기화하지 않는다. 원 proposal/hash는 그대로이고 검토 entries만 명시 채택에 전달한다. Data의 이 optional 공개 인자를 포함한 GUI 변경과 함께 통합해야 한다.

새 표본 정책의 기본 표본 가중치는 1이다. 시험 가중치는 별도 trial 항목에 그대로 남으며 표본 기본값에 다시 곱하지 않는다. 기존 채택 정책을 다시 열 때는 사용자가 정한 표본 가중치를 그대로 복원한다.

GUI 대역 검사 7개: 미확정 값/소유자/호출자 입력 보존, 잘못된 원본과 늦은 세대 거절, 정확 처리 차수/채널 읽기, 구간 정책 무손실, 명시 정책 채택 단일 호출, 유실 응답 재확인/늦은 편집 보존, 기존 표본 용도와 가중치의 재열기. 기존 후보 적용 결과 확인 9개도 통과했다. 실제 Data C1 owner가 내보낸 공개 결과를 Windows 창에서 정상/좁은 크기로 읽고 포커스/Esc/정책 보존을 확인했다. 실제 Data 정책 대화상자도 해당 channel/proposal로 정상/좁은 창과 취소를 확인했다. 이 native 검사의 서비스 읽기는 보존 fixture이며 정책 채택/fit/cold 전체 동선은 root의 Data C2 공통 통합 뒤 별도 확인한다. 계산이나 정책 채택 완료를 이 GUI 검사로 주장하지 않는다. Data C2의 canonical fit consumer 및 공통 입력 스키마는 root/실제 Pro 소유다.

부분 실패 후속은 current main의 private 복사본과 Data 선택 읽기 GUI로 확인했다. 영향 Qt 군집에서 36개가 통과했고 기존 Data 미리보기 색상 의존 한 건은 누락된 파일 때문에 실패했다. 원 실패는 보존했으며 담당 팀에 전달했다. 실제 공개 9행 CSV를 기존 JobManager로 가져온 뒤 지원되는 응력/변형 처리와 지원되지 않는 Cauchy 변환을 함께 보존했다. 실제 loopback 서비스와 Windows 창에서 부분 실패 표시, 선택한 응력/변형 조회, 미확정 `1e`/선택 후 Esc 취소, 시험 가중치 2, 표본별 검증 용도/가중치 1.5의 명시 채택, 저장/재열기까지 확인하고 정상/좁은 화면을 읽었다. 이 native 실행은 마지막 driver의 작업명 오기(`data.import` 대신 실제 `import_table`) 때문에 종료 1이었으며 업무 assertions는 그 전에 통과했다. 원 로그는 그대로 보존했다. 새 Python에서 같은 보존 store의 정확한 source/응답값/정책/저장 차수/부분 실패와 실패 채널 거절을 재조회한 검사는 통과(19.87초, 종료 0, 새 제출 0)했다. 최초 재조회 driver의 잘못된 store 경로 오류도 보존했다. 모든 실행의 private Job은 정리됐다. 관련 기록은 `_workspace/delivery-numerical-pde/partial-current-01/` 및 `partial-focused-process-01`, `partial-native-process-01`, `partial-cold-process-01/02`에 있다. solver/fit 실행은 없으며 물리 검증이나 전체 제품 인도 완료를 뜻하지 않는다.
