# Clickable task scenarios — D1

모든 작업은 합성 planning state 전이다. Qt gallery는 PNG 위 focusable hotspot으로 동작하며 제품 service/solver/provider에 연결하지 않는다. `material_demo.py`는 별도로 table/plot·buffer/owner/save/recovery·CAS 상태를 조작하는 Qt harness다. 실제 Qt 실행 여부는 prototype/VERIFICATION.md를 따른다.

## 사용법

`prototype/Start-PlanningPrototype.ps1`의 Gallery 모드로 시작하고 scenario를 선택한다. SVG는 도형/텍스트 편집 원본, screens.json은 same1440×900 좌표·hotspot·owner·전이·원문 expectation이다. Penpot native 파일은 Codex가 실제 계정/무료 플랜에서 import→프로토타입 연결→export 후 회수한다. 이 ZIP에는 Penpot에서 만들었다고 주장하는 가짜 원본이 없다.

## SC-01 — Material two CSVs → future fit → target adoption → explicit Save / cold reopen

시작 board `HOME-EMPTY`. 마지막 state에서 저장·취소 결과와 남은 실행/dirty owner를 확인한다.

| 단계 | 화면 | 클릭 / hotspot | 다음 화면 | 확인할 결과 |
|---|---|---|---|---|
| 1 | HOME-EMPTY | Data / test files / HOME-EMPTY-06 | DATA-MAP | A/B 원본 열 순서·단위와 raw bytes를 구별한다. |
| 2 | DATA-MAP | Apply mapping / DATA-MAP-03 | DATA-EDIT | numerical conversion과 L0/A0 quantity recipe를 적용한다. |
| 3 | DATA-EDIT | Show invalid sample / DATA-EDIT-07 | DATA-INVALID | 품질 제외/입력 오류/선택범위가 표와 곡선에서 연결된다. |
| 4 | DATA-INVALID | Correct time in recipe / DATA-INVALID-10 | DATA-EDIT | 원파일은 보존하고 해당 recipe draft를 고친다. |
| 5 | DATA-EDIT | Link exact observation r4 / DATA-EDIT-11 | MAT-PROTOCOL | e/P11/time과 traction-free 횡조건의 미지원을 확인한다. |
| 6 | MAT-PROTOCOL | Keep protocol draft / review curves / MAT-PROTOCOL-14 | MAT-DIRTY | 현재 미지원 draft를 저장·편집할 수 있다. |
| 7 | MAT-DIRTY | Fit blocked… / MAT-DIRTY-05 | MAT-PROTOCOL | current adapter가 미지원 입력을 실행하지 않는다. |
| 8 | MAT-PROTOCOL | Preview proposed ready state / MAT-PROTOCOL-16 | MAT-READY | 향후 지원된 별도 모의 입력 branch를 명시 선택한다. |
| 9 | MAT-READY | Run fit… / MAT-READY-05 | MAT-FIT-RUNNING | fixed source/Plan/mask/budget의 미래 지원 모의 실행. |
| 10 | MAT-FIT-RUNNING | Simulate partial completion / MAT-FIT-RUNNING-16 | MAT-FIT-PARTIAL | c017/c014/c009/c021의 보존·누락·실패·취소를 구별한다. |
| 11 | MAT-FIT-PARTIAL | Adopt candidate c017… / MAT-FIT-PARTIAL-15 | MAT-ADOPT-CONFLICT | source r17/candidate/current target r18의 3-way diff. |
| 12 | MAT-ADOPT-CONFLICT | Cancel / keep current / MAT-ADOPT-CONFLICT-03 | MAT-FIT-PARTIAL | 후보·현재 target·원본 결과는 바뀌지 않는다. |
| 13 | MAT-FIT-PARTIAL | Adopt candidate c017… / MAT-FIT-PARTIAL-15 | MAT-ADOPT-CONFLICT | 다시 명시 target을 검토한다. |
| 14 | MAT-ADOPT-CONFLICT | Propose c017 on current r18… / MAT-ADOPT-CONFLICT-01 | MAT-ADOPT-DRAFT | 검토한 변경을 fresh CAS로 target draft에 Apply. saved r18/.900은 유지한다. |
| 15 | MAT-ADOPT-DRAFT | Save acknowledged Material draft / MAT-ADOPT-DRAFT-04 | MAT-ADOPT-SAVED | 명시 Save만 r19/.862와 adoption receipt를 게시한다. Plan r8은 유지. |
| 16 | MAT-ADOPT-SAVED | Cold reopen saved r19 / MAT-ADOPT-SAVED-02 | REOPEN-MAT-ADOPTED | 새 owner가 r19/.862와 이전 r17 fit 근거를 읽는다. fit/provider 재실행 없음. |
| 17 | REOPEN-MAT-ADOPTED | Open retained result / REOPEN-MAT-ADOPTED-02 | MAT-FIT-PARTIAL | 보존 fit은 frozen r17에서 온 결과로 계속 표시한다. |

**수용 기록:** 클릭 성공 여부와 별개로 selection/value/owner/ref/dirty/result availability를 기록한다. 막힌 버튼을 건너뛰어 실제 계산 성공으로 보고하지 않는다. screenshot/record는 정확한 board·fixture·실행환경과 함께 남긴다.

## SC-02 — Contact face sets → supported future path → result → r13 rebind cancel/apply → reopen

시작 board `PRE-DESIGN`. 마지막 state에서 저장·취소 결과와 남은 실행/dirty owner를 확인한다.

| 단계 | 화면 | 클릭 / hotspot | 다음 화면 | 확인할 결과 |
|---|---|---|---|---|
| 1 | PRE-DESIGN | FEM / PRE-DESIGN-05 | PRE-FEM | 같은 native 문서에서 해석 입력을 만든다. |
| 2 | PRE-FEM | Contact pair… / PRE-FEM-12 | PRE-CONTACT | A4/B2 면·normal·friction/gap 설정. |
| 3 | PRE-CONTACT | Check capability / PRE-CONTACT-13 | PRE-CONTACT-UNSUPPORTED | 현재 bounded CCX admission 미지원은 Run/export 차단. |
| 4 | PRE-CONTACT-UNSUPPORTED | Return to face sets / PRE-CONTACT-UNSUPPORTED-16 | PRE-CONTACT | 설정 draft를 유지한다. |
| 5 | PRE-CONTACT | Preview supported path / PRE-CONTACT-16 | PRE-CONTACT-READY | 명시 future-supported 모의 branch 선택. |
| 6 | PRE-CONTACT-READY | Freeze valid contact input (simulated) / PRE-CONTACT-READY-14 | RUN-CONTACT | contact-031/attempt02, geometryr12/meshr6/contactr7 고정. |
| 7 | RUN-CONTACT | Simulate completed contact result / RUN-CONTACT-05 | POST-CONTACT | 같은 result/time/pressure1.42/gap−.006/penetration.006/normal112N. |
| 8 | POST-CONTACT | Repair contact after split / POST-CONTACT-12 | PRE-CONTACT-REBIND | current geometryr13 oldr12ghost, split/normalflip preview. |
| 9 | PRE-CONTACT-REBIND | Cancel rebind / PRE-CONTACT-REBIND-14 | PRE-CONTACT-CANCELLED | geometryr13 유지, oldr12contactrefs unresolved, mesh stale. CAD편집을 되돌리지 않는다. |
| 10 | PRE-CONTACT-CANCELLED | Review rebind again / PRE-CONTACT-CANCELLED-02 | PRE-CONTACT-REBIND | 끊긴 해당 대상만 다시 선택한다. |
| 11 | PRE-CONTACT-REBIND | Apply selected rebind / PRE-CONTACT-REBIND-13 | PRE-CONTACT-REBOUND | geometryr13/contactdraft r8 A5/B2 + 명시 orientation. mesh는 여전히r12라 Run차단. |
| 12 | PRE-CONTACT-REBOUND | Save project / PRE-CONTACT-REBOUND-01 | REOPEN-CONTACT-R13 | r13/r8과 oldr12 result를 함께 보존하고 cold reopen. |
| 13 | REOPEN-CONTACT-R13 | Continue editing the same owner / REOPEN-CONTACT-R13-05 | PRE-CONTACT-REBOUND | 재개 시 r13을 유지하며 remesh/preflight 다음 행동을 보여준다. |

**수용 기록:** 클릭 성공 여부와 별개로 selection/value/owner/ref/dirty/result availability를 기록한다. 막힌 버튼을 건너뛰어 실제 계산 성공으로 보고하지 않는다. screenshot/record는 정확한 board·fixture·실행환경과 함께 남긴다.

## SC-03 — Post: external data → measurement → mapping masks → repair

시작 board `POST-OPEN`. 마지막 state에서 저장·취소 결과와 남은 실행/dirty owner를 확인한다.

| 단계 | 화면 | 클릭 / hotspot | 다음 화면 | 확인할 결과 |
|---|---|---|---|---|
| 1 | POST-OPEN | Reader Properties → Apply / POST-OPEN-12 | POST-MEASURE | 실제 reader 설정/선택/값/actual time의 설계를 확인한다. |
| 2 | POST-MEASURE | Compare exact source B / POST-MEASURE-11 | POST-COMPARE | A/B source·quantity/space/time/units를 확인한다. |
| 3 | POST-COMPARE | Preview / validate mapping / POST-COMPARE-10 | POST-MAP-PREVIEW | B→A interpolated 값, outside mask, 0분모와 delta mask를 구별한다. |
| 4 | POST-MAP-PREVIEW | Reset preview / POST-MAP-PREVIEW-12 | POST-MEASURE | 미적용 mapping preview만 취소한다. |
| 5 | POST-MEASURE | Compare exact source B / POST-MEASURE-11 | POST-COMPARE | 기존 reader/measurement를 유지한다. |
| 6 | POST-COMPARE | Preview / validate mapping / POST-COMPARE-10 | POST-MAP-PREVIEW | 현재 refs로 새 preview를 만든다. |
| 7 | POST-MAP-PREVIEW | Apply valid recipe / POST-MAP-PREVIEW-11 | POST-COMPARE | recipe/mask 한 변경과 Undo 범위를 확인한다. |
| 8 | POST-COMPARE | Repair sources / POST-COMPARE-07 | POST-REPAIR | 같은 bytes 이동과 한 frame 변경·누락을 분리한다. |
| 9 | POST-REPAIR | Repair identical files / POST-REPAIR-10 | POST-MEASURE | 동일 bytes 위치만 수리; changed B는 자동 대체하지 않는다. |
| 10 | POST-MEASURE | Keep measurement + Save analysis / POST-MEASURE-12 | REOPEN-POST | 정의/마스크/값/뷰를 저장하고 새 owner에서 연다. |

**수용 기록:** 클릭 성공 여부와 별개로 selection/value/owner/ref/dirty/result availability를 기록한다. 막힌 버튼을 건너뛰어 실제 계산 성공으로 보고하지 않는다. screenshot/record는 정확한 board·fixture·실행환경과 함께 남긴다.

## SC-04 — Dirty buffers / partial save / close versus job cancel

시작 board `MAT-DIRTY`. 마지막 state에서 저장·취소 결과와 남은 실행/dirty owner를 확인한다.

| 단계 | 화면 | 클릭 / hotspot | 다음 화면 | 확인할 결과 |
|---|---|---|---|---|
| 1 | MAT-DIRTY | Review source / save conflict / MAT-DIRTY-14 | CLIENT-CONFLICT | buffer와 remote current, acknowledged draft를 나란히 본다. |
| 2 | CLIENT-CONFLICT | Read current / keep buffer / CLIENT-CONFLICT-01 | MAT-DIRTY | 로컬 원문을 덮어쓰지 않는다. |
| 3 | MAT-DIRTY | Save both… / MAT-DIRTY-03 | SAVE-PARTIAL | per-owner receipt와 이전 saved revision을 본다. |
| 4 | SAVE-PARTIAL | Close with recovery choices… / SAVE-PARTIAL-05 | CLOSE-DIRTY | 문서 저장과 job 취소가 별개다. |
| 5 | CLOSE-DIRTY | Inspect separate job cancellation… / CLOSE-DIRTY-05 | RUN-CANCEL | cancel requested와 terminal을 구별한다. |
| 6 | RUN-CANCEL | Close window separately… / RUN-CANCEL-10 | CLOSE-DIRTY | 종료 미확인은 그대로 남긴다. |
| 7 | CLOSE-DIRTY | Keep recovery drafts and close / CLOSE-DIRTY-02 | RECOVERY-REOPEN | invalid raw buffer를 recovery capsule로 보존한다. |
| 8 | RECOVERY-REOPEN | Recover raw unsaved draft / RECOVERY-REOPEN-02 | CLIENT-CONFLICT | 원문/base refs를 새 dirty session에서 검토한다. |

**수용 기록:** 클릭 성공 여부와 별개로 selection/value/owner/ref/dirty/result availability를 기록한다. 막힌 버튼을 건너뛰어 실제 계산 성공으로 보고하지 않는다. screenshot/record는 정확한 board·fixture·실행환경과 함께 남긴다.

## SC-05 — Assembly preview → restore failure → design recovery

시작 board `PRE-DESIGN`. 마지막 state에서 저장·취소 결과와 남은 실행/dirty owner를 확인한다.

| 단계 | 화면 | 클릭 / hotspot | 다음 화면 | 확인할 결과 |
|---|---|---|---|---|
| 1 | PRE-DESIGN | Assembly / PRE-DESIGN-04 | PRE-MOTION | native 설계 P0와 view preview P1을 구별한다. |
| 2 | PRE-MOTION | Pause preview / PRE-MOTION-12 | PRE-MOTION | 표시 frame은 유지되고 설계는 P0다. |
| 3 | PRE-MOTION | Simulate restore failure / PRE-MOTION-15 | PRE-RESTORE-FAILED | 저장/FEM/export/run 차단, 실제 pose 대조를 요구한다. |
| 4 | PRE-RESTORE-FAILED | Reconnect / compare actual pose / PRE-RESTORE-FAILED-12 | PRE-MOTION | same current owner/session/generation을 다시 읽는다. |
| 5 | PRE-MOTION | Restore design pose / PRE-MOTION-13 | PRE-DESIGN | P0 복원 성공 상태로 돌아간다. |
| 6 | PRE-DESIGN | Save project / PRE-DESIGN-02 | REOPEN-CONTACT | cold reopen은 설계 pose에서 시작한다. |

**수용 기록:** 클릭 성공 여부와 별개로 selection/value/owner/ref/dirty/result availability를 기록한다. 막힌 버튼을 건너뛰어 실제 계산 성공으로 보고하지 않는다. screenshot/record는 정확한 board·fixture·실행환경과 함께 남긴다.

## SC-06 — Independent PDE / Evaluation / nonconvergence and reuse

시작 board `PDE-EQUATION`. 마지막 state에서 저장·취소 결과와 남은 실행/dirty owner를 확인한다.

| 단계 | 화면 | 클릭 / hotspot | 다음 화면 | 확인할 결과 |
|---|---|---|---|---|
| 1 | PDE-EQUATION | Check expression / PDE-EQUATION-03 | PDE-INVALID | 식 오류/BC 누락과 미지원 weak form을 구별한다. |
| 2 | PDE-INVALID | Correct symbol / boundary / PDE-INVALID-09 | PDE-EQUATION | 그 node/cell에서 수정한다. |
| 3 | PDE-EQUATION | Evaluation definition / PDE-EQUATION-06 | EVAL-STAGES | 기존 same Evaluation editor를 Plan 없이 연다. |
| 4 | EVAL-STAGES | Edit same transfer owner / EVAL-STAGES-10 | EVAL-TRANSFER | Kelvin SI bounded stage refs, exact same mesh를 검토한다. |
| 5 | EVAL-TRANSFER | Return to stages / EVAL-TRANSFER-09 | EVAL-STAGES | exact SI field/lag0/seeded lag1/check를 보존한다. |
| 6 | EVAL-STAGES | Evaluate once / EVAL-STAGES-06 | RUN-EVALUATION | 같은 E-02r5 / eval-019 attempt02를 연다. |
| 7 | RUN-EVALUATION | Simulate NOT_CONVERGED result / RUN-EVALUATION-05 | EVAL-NONCONVERGED | 프로세스 종료와 전체 연성 잔차 판정의 별도 합성 상태를 확인한다. |
| 8 | EVAL-NONCONVERGED | Edit iteration policy (new input) / EVAL-NONCONVERGED-09 | EVAL-STAGES | downstream edit도 전체 definition hash 변경, 현재 prefix reuse 불가. |
| 9 | EVAL-STAGES | Iterations / EVAL-STAGES-05 | EVAL-NONCONVERGED | 보존 실행의 미수렴은 그대로다. |
| 10 | EVAL-NONCONVERGED | Save definition and convergence evidence / EVAL-NONCONVERGED-12 | REOPEN-EVALUATION | 미수렴/잔차/단계 상태를 보존하고 재실행하지 않는다. |

**수용 기록:** 클릭 성공 여부와 별개로 selection/value/owner/ref/dirty/result availability를 기록한다. 막힌 버튼을 건너뛰어 실제 계산 성공으로 보고하지 않는다. screenshot/record는 정확한 board·fixture·실행환경과 함께 남긴다.

## SC-07 — Numerical methods / failed candidates / UQ / surrogate / MOO

시작 board `NUM-DOE`. 마지막 state에서 저장·취소 결과와 남은 실행/dirty owner를 확인한다.

| 단계 | 화면 | 클릭 / hotspot | 다음 화면 | 확인할 결과 |
|---|---|---|---|---|
| 1 | NUM-DOE | Sensitivity / NUM-DOE-09 | NUM-SENSITIVITY | DOE 회귀와 SALib Sobol matched design을 구별한다. |
| 2 | NUM-SENSITIVITY | UQ / NUM-SENSITIVITY-10 | NUM-UQ | 분포/독립가정/실패표본과 조건부 통계를 확인한다. |
| 3 | NUM-UQ | Surrogate / NUM-UQ-11 | NUM-SURROGATE | train/holdout disjoint, PREDICTED와 out-of-range를 본다. |
| 4 | NUM-SURROGATE | Multiobjective / NUM-SURROGATE-12 | NUM-MOO | Pareto와 infeasible 후보를 동시에 보존한다. |
| 5 | NUM-MOO | Adopt selected… / NUM-MOO-06 | NUM-ADOPT-CONFLICT | owner별 explicit target revision proposal을 검토한다. |

**수용 기록:** 클릭 성공 여부와 별개로 selection/value/owner/ref/dirty/result availability를 기록한다. 막힌 버튼을 건너뛰어 실제 계산 성공으로 보고하지 않는다. screenshot/record는 정확한 board·fixture·실행환경과 함께 남긴다.

## SC-08 — External batch / remote disconnect / same attempt identity

시작 board `NUM-BATCH`. 마지막 state에서 저장·취소 결과와 남은 실행/dirty owner를 확인한다.

| 단계 | 화면 | 클릭 / hotspot | 다음 화면 | 확인할 결과 |
|---|---|---|---|---|
| 1 | NUM-BATCH | Run / analyze / NUM-BATCH-04 | RUN-NUM-BATCH | 정확 exchange/candidate refs로 등록한 attempt를 연다. |
| 2 | RUN-NUM-BATCH | Locations / RUN-NUM-BATCH-03 | RUN-REMOTE-CONFIG | 자원/host와 물리 수치정책을 분리한다. |
| 3 | RUN-REMOTE-CONFIG | Inspect reconnect / result staging scenario / RUN-REMOTE-CONFIG-07 | RUN-REMOTE-LOST | remote 종료를 추정하지 않는다. |
| 4 | RUN-REMOTE-LOST | Inspect transferred / partial artifacts / RUN-REMOTE-LOST-08 | NUM-BATCH | FAILED/NOT_EVALUATED/ID CONFLICT를 0응답으로 바꾸지 않는다. |
| 5 | NUM-BATCH | Save Plan / reopen without rerun / NUM-BATCH-16 | REOPEN-NUM-BATCH | staging receipts와 원입력을 재열기한다. |

**수용 기록:** 클릭 성공 여부와 별개로 selection/value/owner/ref/dirty/result availability를 기록한다. 막힌 버튼을 건너뛰어 실제 계산 성공으로 보고하지 않는다. screenshot/record는 정확한 board·fixture·실행환경과 함께 남긴다.

## SC-09 — Physical measurement → Study → providerless Expert / next Plan

시작 board `DATA-CALIBRATION`. 마지막 state에서 저장·취소 결과와 남은 실행/dirty owner를 확인한다.

| 단계 | 화면 | 클릭 / hotspot | 다음 화면 | 확인할 결과 |
|---|---|---|---|---|
| 1 | DATA-CALIBRATION | Add Study evidence / DATA-CALIBRATION-10 | STUDY-DECISION | registered source와 exact locator를 근거에 연결한다. |
| 2 | STUDY-DECISION | Discuss (optional) / STUDY-DECISION-05 | EXPERT-DRAFT | provider 미연결에서도 질문·기존 근거를 연다. |
| 3 | EXPERT-DRAFT | Save reply draft / EXPERT-DRAFT-14 | REOPEN-EXPERT | LLM 호출 없이 draft를 보존한다. |
| 4 | REOPEN-EXPERT | Open linked Study / REOPEN-EXPERT-07 | STUDY-DECISION | 판단을 자동 바꾸지 않는다. |
| 5 | STUDY-DECISION | Create editable Plan proposal / STUDY-DECISION-14 | NUM-NEXT-TEST | 다음 구별 시험 Plan을 실제 owner에서 편집한다. |

**수용 기록:** 클릭 성공 여부와 별개로 selection/value/owner/ref/dirty/result availability를 기록한다. 막힌 버튼을 건너뛰어 실제 계산 성공으로 보고하지 않는다. screenshot/record는 정확한 board·fixture·실행환경과 함께 남긴다.

## SC-10 — Nonlinear / explicit / failure scope and current admission

시작 board `SIM-IMPLICIT`. 마지막 state에서 저장·취소 결과와 남은 실행/dirty owner를 확인한다.

| 단계 | 화면 | 클릭 / hotspot | 다음 화면 | 확인할 결과 |
|---|---|---|---|---|
| 1 | SIM-IMPLICIT | Explicit / SIM-IMPLICIT-04 | SIM-EXPLICIT | IC/energy/timestep/added mass 출력 의미를 확인한다. |
| 2 | SIM-EXPLICIT | Failure / interface / SIM-EXPLICIT-05 | SIM-FAILURE | bulk/interface/재닫힘/fatigue 제한을 구별한다. |
| 3 | SIM-FAILURE | Inspect capabilities / runtime / SIM-FAILURE-08 | SETUP-CAPABILITY | 등록/무료경로/실제실행 미확인을 구별한다. |
| 4 | SETUP-CAPABILITY | Keep working with saved data / SETUP-CAPABILITY-08 | HOME-EMPTY | 미지원 물리 때문에 독립 문서 작업을 막지 않는다. |

**수용 기록:** 클릭 성공 여부와 별개로 selection/value/owner/ref/dirty/result availability를 기록한다. 막힌 버튼을 건너뛰어 실제 계산 성공으로 보고하지 않는다. screenshot/record는 정확한 board·fixture·실행환경과 함께 남긴다.

## SC-11 — Optional Workbench / same owner / source revision

시작 board `WB-LINKS`. 마지막 state에서 저장·취소 결과와 남은 실행/dirty owner를 확인한다.

| 단계 | 화면 | 클릭 / hotspot | 다음 화면 | 확인할 결과 |
|---|---|---|---|---|
| 1 | WB-LINKS | Open Material owner / WB-LINKS-06 | MAT-DIRTY | copy 없이 기존 Material owner를 연다. |
| 2 | MAT-DIRTY | Open same Plan / MAT-DIRTY-13 | NUM-OPTIMIZE | embedded와 standalone Plan이 같다. |
| 3 | NUM-OPTIMIZE | Evaluation editor / NUM-OPTIMIZE-03 | EVAL-STAGES | 같은 Evaluation owner/editor를 연다. |
| 4 | EVAL-STAGES | Save definition / EVAL-STAGES-02 | REOPEN-EVALUATION | 정확 참조를 유지한 채 저장·재개한다. |

**수용 기록:** 클릭 성공 여부와 별개로 selection/value/owner/ref/dirty/result availability를 기록한다. 막힌 버튼을 건너뛰어 실제 계산 성공으로 보고하지 않는다. screenshot/record는 정확한 board·fixture·실행환경과 함께 남긴다.

## SC-12 — Hardware unavailable / file-based calibration / evidence report

시작 board `DEVICE-PLAN`. 마지막 state에서 저장·취소 결과와 남은 실행/dirty owner를 확인한다.

| 단계 | 화면 | 클릭 / hotspot | 다음 화면 | 확인할 결과 |
|---|---|---|---|---|
| 1 | DEVICE-PLAN | Import existing measurement file / DEVICE-PLAN-06 | DATA-CALIBRATION | 기기 제어 없이 file loop를 완성한다. |
| 2 | DATA-CALIBRATION | Open registered original / DATA-CALIBRATION-08 | REPORT-REVIEW | 교정 원문/누락/실패 근거를 확인한다. |
| 3 | REPORT-REVIEW | Keep draft and return to Study / REPORT-REVIEW-09 | STUDY-DECISION | UNKNOWN과 NOT_RELEASED를 보존한다. |
| 4 | STUDY-DECISION | Save explicit research decision / STUDY-DECISION-12 | REOPEN-STUDY | 명시 판단을 보존하고 새 owner에서 읽는다. |

**수용 기록:** 클릭 성공 여부와 별개로 selection/value/owner/ref/dirty/result availability를 기록한다. 막힌 버튼을 건너뛰어 실제 계산 성공으로 보고하지 않는다. screenshot/record는 정확한 board·fixture·실행환경과 함께 남긴다.

## Qt에서 별도로 확인할 조작

표 키보드(F2/Enter/Tab/Esc), 범위 선택과 plot 선택, owner별 Ctrl+S, Material+Plan partial save, raw invalid recovery, source refresh 취소/적용, revision conflict 재검토/분기/취소, close와 job cancel 분리. 보존결과 선택은 새 eval ID를 만들지 않고 명시 detail만 새 ID를 만든다. 실제 native3D·dock/DPI/파일 chooser는 이 Gallery 클릭만으로 검증되지 않는다.

## Penpot 작성/회수 인계

1. 실제 무료 계정 접근을 확인한다. 보드별 SVG를 import하되 bitmap flatten으로 편집 원본을 대신하지 않는다.
2. screens.json의 layer IDs/좌표/텍스트와 SVG text를 대조하고 공통 tokens/components를 만든다.
3. 각 hotspot bounds를 interactive rectangle으로 만들고 target board를 정확 ID로 연결한다. 일반 click 전이가 기본이며 Esc/back는 scenario 복귀 제어다. 제품 drag와 double-click 설계는 SCREEN_SPEC와 본문을 따른다.
4. SC-01–12에서 실패/취소/재열기 branch를 실제 클릭한다. 지원되지 않는 Penpot interaction은 Notes에 제한을 기록하고 Qt harness에서 검토한다.
5. native .penpot와 SVG/PNG export를 local로 회수하고 export version/hash/실제 클릭 기록을 CURRENT_STATE에 연결한다. 파일 다운로드만으로 Windows Qt/native/solver 검증을 대체하지 않는다.