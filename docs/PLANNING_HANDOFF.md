# 기능에서 구현과 검증까지

2026-10-08. 본 구현 착수용 작업 분해. 제품 상세 설계는 `PLANNING_DESIGN.md`, 화면은 `PLANNING_SCREENS.md`, 데이터는 `PLANNING_CONTRACTS.md`, 코드와 재사용 근거는 `PLANNING_CODE_REUSE.md`다. 아래 작업은 이번 시안과 실제 제품의 차이를 닫는 단위다. 시안의 존재가 이 작업의 완료는 아니다.

## 구현 순서와 완료 행동

| 작업 | 선행조건 | 기능 → 화면/명령 | 데이터/API → 변경 위치 | 완료 기준 |
|---|---|---|---|---|
| D01 문서 수명·직접 실행 | 상세 계약 검토 | 6개 시작 항목, 파일 열기/저장/닫기/재개 | revision/expected_revision, LaunchRequest → `scripts/start-windows.ps1`, `apps/lab/server.py`, 신규 `caelab/documents.py`, `apps/lab/static/documents/` | Workbench 종료 상태에서 각 앱 launch. 다른 파일 두 개 작업·저장·종료·서버재기동·재열기. 두 창 충돌409, 한글 경로, schema major 진단 |
| D02 선택·뷰어 공통 경계 | D01, 실제 선택 가능한 reader | tree/central/property 같은 객체, 표시/숨김·rename | selection `{document,id,kind}`, stable entity map → `adapters/native_face_catalog.py`, `analysis_conditions.py`, `apps/lab/static/viewers/` | 동일 dataset의 면/cell/절점 또는 구간 선택이 양방향 일치하고 저장 후 ID 유지. topology 변경 시 끊어진 조건을 진단 |
| D03 실험/재료 전처리 | D01 | 가져오기 매핑, 곡선/구간, 단위·가중치, 재료점 이력 | `file_table.preview_table/read_table`, prep→Case → `adapters/file_table.py`, `model_parameters.py`, 신규 `apps/lab/static/preprocessor/` | 다른 CSV 2개(비정상행 포함), 단위 변환과 제외 구간의 원본 보존, Undo, 검증→실행기 전달. CAD/AI 없음 |
| D04 PDE/mesh/조건 전처리 | D02 | 영역/식/약형식/mesh set, 재료·하중·구속 배정 | adapter `describe_inputs/bind_inputs`, condition target IDs → `pde.py`, `analysis_conditions.py`, `condition_parameters.py`, native adapters | 면 선택→조건 적용→표시/트리→Undo→저장/재열기. 미지원 카드/식 사전 거절. 범용 solver 덱 자동 변환 약속 금지 |
| D05 솔버 실행기 | D01,D03 또는 D04 | 입력검사, queue/run/cancel, 로그·수렴, 실패 위치, 재실행 | `JobManager.submit/status/cancel/result`, 고정 input revision → `jobs.py`, `execution_control.py`, `apps/lab/workbench_routes.py`, 신규 runner UI | 실제 지원 backend 1개 실행, 틀린 입력·취소·프로세스 실패 각각 관찰. 앱 종료에도 job 유지, 재기동 INTERRUPTED 처리, 재실행 새 ID |
| D06 후처리·외부 ASCII | D01,D02,D05 선택 | component/frame/location/legend, curve overlay/probe/export | `read_result`, `response_history/field/comparison` → 기존 response 파일, `native_responses.py`, 신규 post UI | solver 없는 환경에서 저장 결과+ASCII 읽기; 두 run 시간 동기/비동기 비교; 단위/좌표계 불일치 경고; 추출값과 원 수치 일치 |
| D07 평가 절차·DOE·동정 | D01,D03,D05,D06 | 노드 입출력, 변수·목적·제약, 예산, 후보실패·재평가 | existing `Workbench`, `numerical.fit_model/optimize`, SciPy → `workbench.py`, `numerical.py`, `optimizers/`, 신규 study UI | 2변수 이상 실제 평가기/복수 시험 동정, held-out 검증과 학습오차 구분, failed candidate 보존, 선택 후보가 같은 run/curve를 연다 |
| D08 UQ·민감도·대리모델 | D07 | 분포/상관, 분석방법, 범위/오차, Pareto/후보 상세 | SALib plan provenance, `analyze_candidates/fit_surrogate` → `numerical.py`, `optimizers/probabilistic_analysis.py`, study UI | LHS를 Sobol로 잘못 분석하면 거절. 실패행 유지. 실제/예측/외삽 표시. 최종 후보 native 재계산 연결 |
| D09 실제 전문가 채팅 | D01, 승인된 endpoint 별도 | 세션/발언/reply/중간개입/진행자/논점/근거 | `ExpertRuntime`, message sequence, session evidence → `assist/experts.py`, `knowledge.py`, `literature.py`, 신규 expert UI | 자유 질문→2관점 발언→사용자 추가 관측→그 내용 참조한 후속 발언→세션 재개. 모델 미설정과 생성실패 별도. 고정 문장으로 통과 불가 |
| D10 전문가 실행 제안 왕복 | D07,D09 | 계획 검토·수정·실행, 완료결과 대화로 돌리기 | scope/proposal/job refs → `research_context.py`, `workbench.py`, experts와 study UI | 제출영수증/실제결과 구분. 허용 범위 변경시에만 재검토. 긴 job 동안 대화 대기로 worker 교착 없음 |
| D11 Workbench 연결 | D01,D05,D07 | typed-port 연결, 객체 버전 열기, stale/영향/재연결 | document.saved/dependency graph → 신규 `caelab/project_graph.py`, `workbench_routes.py`, Workbench UI | 단독 저장물 등록→정확 버전→상위수정→해당 하위만 stale→수동 새 실행→이전결과 보존→프로젝트 재개. 순환/단위/파일오류 표시 |
| D12 배포·검증·이관 | D01~11 | 설치, 시작, 도움말, 지원능력 진단 | capability/health endpoint → 기존 install/start/doctor 및 `docs/LOCAL_EXECUTION.md` | stock Windows 계정에서 6앱 시작. 선택 solver/LLM 미설정에도 독립도구 완결. 실제 화면 1440×900 및 작은 창 검토. 네이티브/웹 이중 GUI 없음 |

신규 경로는 제안된 구현 위치이며 이미 코드가 있다는 의미가 아니다. D03/06은 CAD·native 솔버 자원 없이 먼저 완결할 수 있다. D09 실제 모델 조건이 없어도 D01~08·11을 진행한다. 기존 R1–R5 수치/네이티브 문제는 해당 backend 작업과 같이 추적하고 GUI 시연으로 완료 처리하지 않는다.

## 제품 범위를 화면에 보존

| 기존 사례 | 상세 대상과 주요 명령 | 위 작업 |
|---|---|---|
| UC01 시간 의존 재료·UC02 반복소성 | 시험별 이력/초기상태, 동정용/확인용 분리, 루프/완화곡선 비교 | D03,D07 |
| UC03 적분/접선 실패 | 실패증분 분리, 초기상태 복제, 옵션별 실제 잔차/접선 비교 | D04,D05,D06 |
| UC04 PDE | 영역·약형식·경계조건, 격자/해법 변경, 잔차와 공간오차 별도 | D04,D05,D06 |
| UC05 충격·UC07 박리·UC08 접촉 | 덱/mesh/재료·접촉조건, 에너지·힘·변위·손상 이력, 실패위치 | D04,D05,D06 |
| UC09 구조/지그 | geometry/mesh 변수, 하중·구속, 질량/강성/가공제약 | D02,D04,D07 |
| UC10 상관·UC17 외부출력 | ASCII mapping, 시간·좌표계·위치, 구간오차, 후보/시험 ID | D03,D06,D07,D11 |
| UC11 UQ/민감도·UC13 대리/Pareto | 출처 있는 분포/표본계획, 실패율, 예측범위/확인오차 | D08 |
| UC12 다음 시험·UC15 논문 재현 | 자료/가정/원문위치, 평가계획·예측차·측정오차, 재현조건 | D07,D09,D10 |
| UC06 과열·UC14 VOC 자문 | 변경이력·관측, 가설/반론/근거, 필요한 확인과 실행제안 | D09,D10 |
| UC16 미세조직/연성/원격 확장 | 목적에 맞는 외부평가기/자원·결과 import | D05,D06,D07 이후 확장. 임의 HPC 지원 약속 아님 |

## 시각 검토에 사용할 기준

각 흐름은 실제 UI에서 조작과 캡처로 확인한다. 파일 존재·DOM 검사·단위테스트 수는 시각 검토 대체가 아니다. 별도 검토자가 사용자 요구와 화면을 비교하고 root가 수정 결과를 통합한다. 현재 결과는 `WORKBENCH_PROGRESS.md`의 같은 절에 유지한다.

전체 기획 합격에는 전체 구조, 화면·주요 명령/상태, 단독 저장·재개, 연결 계약, 참고 행동/재사용 선택, 시안 관찰, 위 코드 경로별 작업이 모두 필요하다. 실제 LLM·대규모 solver와 시안 대체동작은 구분한다. 남은 핵심 동작이 정의되지 않았거나 화면으로 확인되지 않았으면 해당 부분은 미완료다.
