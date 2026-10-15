# Impact Input A — 구현 연결과 인도 경계

요청: PRO-IMPACT-INPUT-A-20261015-01. 기준은 ce9ec3aefc6b7bc759b7b6bda23177595dbd3cd1, fixture는 3e48bf6138f495299f45b1af254bfb4aaff307b8이다. 이 디렉터리는 새 전용 문서다. CURRENT_STATE와 기존 전사 배정·진행 표를 수정하지 않았다. B/C 전체 잔여의 완료 표시도 바꾸지 않았다.

## 실제 연결

`impact_source.capture`가 original byte/file/line/include occurrence를 보관한다. `impact_input_edits`는 그 원본 범위와 before/after hunk를 분리한다. 계층 INP는 `impact_assembly`에서 instance/local → effective ID와 material/sets/faces/fixed-DOF lineage를 생성하고 기존 INP2RAD에 **별도 compile 결과**를 전달한다. RAD는 `impact_rad_source`의 Starter/Engine include graph 및 `impact_native`의 field/reference admission을 거쳐 **수정한 원 byte를 그대로** export한다. RAD 경로는 INP2RAD를 호출하지 않는다.

`impact_input_workflow`의 값 반환을 사용자가 명시 Apply하면 기존 `simulation.update`로 같은 문서를 갱신한다. `simulation.evaluate` → 기존 Workbench/JobManager → `ImpactAdapter` → 기존 owned Starter/Engine → 기존 TH/ANIM converter와 `impact_results`로 이어진다. 런타임 발견/실행을 가져오기·표시·편집·저장에 끼워 넣지 않았다. 새 owner/controller/store/solver/서버를 만들지 않았다.

`impact_retained`는 기존 impact_execution.json에 원 입력·원 출력·개별 VTK frame pin과 metadata를 추가한다. Dynamic C2의 **일반 파일 pin, 경로/handle 각각의 stamp, 두-pass hash**만 재사용한다. 실제 RAD 데이터 문법/TH/ANIM/time는 기존 impact reader가 처리한다. FRD parser를 재명명하거나 공용 Dynamic reader를 RAD reader로 사용하지 않는다. 개별 frame 선택은 해당 VTK payload를 실제 검증하고, metadata 조회를 VERIFIED로 올리지 않는다.

기존 Simulation 저장 revision의 결과 사본을 새 owner가 읽는다. 재계산 없이 보존 VTK/CSV를 읽는 `simulation.reprocess`는 기존 JobManager의 별도 `impact.reprocess` 작업이며, 원 execution status와 source job/input을 고정한다. 명시 `convert_raw=True`일 때만 동일 pinned ANIM/TH converter 두 개를 허용한다. 이 모듈에서 Starter/Engine는 호출할 수 없다. 원 실패를 새 읽기 성공으로 덮지 않는다.

## 파일·작성 경계

Pro 전용 domain/adapters/tests/examples/docs만 full source와 product.patch에 있다. Workbench, MaterialDocuments/SimulationDocuments, native_responses, evaluation의 변경은 root-integration.patch에만 있다. apps 아래 GUI 파일은 하나도 수정하지 않았다. GUI_CONNECTION_PROPOSAL.md는 Sol 적용용이며 현재 실행 가능한 Qt 구현/Windows UX 검증이라고 주장하지 않는다. protected 후속 f2b4a5c의 Data/Runner GUI·기존 사용법을 ce9 전체파일로 되돌리지 않는다.

공통 변경은 원문 멤버 경로의 제한된 admission, 기존 문서의 실행 command 확장 hook/읽기 Job, impact native 응답 dispatch, source 진단 위치, 원행 번호의 JSON 가능한 scalar 반환이다. 마지막 변경은 행 번호·값을 바꾸지 않고 numpy scalar를 Python scalar로 꺼내는 2행 hunk다. 기존 owner와 원 job idempotency/lost-reply 계약을 유지한다.

## 전체 완료가 아닌 이유

이 인도는 첫 elastic C3D4 계층/native 입력의 실행·보존·선택 읽기 core와 실제 runnable 경로다. `/RBODY`의 solver 이산 질량/전체 관성/COM 및 주축 readback, native `/TRANSFORM` 및 `/INIVEL/AXIS`의 실행 admission은 **미구현/차단**이다. 현재 C3D4 체적 적분으로 산출한 COM/전체 관성은 입력으로 계산한 연속체 물리량이지 native 강체의 이산 질량행렬 결과가 아니다. 회전 자세와 ω를 INP 초기 절점 속도에 반영하는 것은 강체 구속을 생성하지 않는다.

Windows Starter→Engine→TH/ANIM→실제 ParaView 화면, Qt 조작, 실제 native 실패 재변환은 이 작성환경에서 NOT_RUN이다. A 전체 인수/공학 승인/일반 arbitrary assembly 지원을 완료로 표시하지 않는다. B bulk damage/계면 재접촉 전체, C ε–N/mean/critical-plane은 별도 잔여이며 기존 LAW117 및 fatigue 경로는 유지했다.
