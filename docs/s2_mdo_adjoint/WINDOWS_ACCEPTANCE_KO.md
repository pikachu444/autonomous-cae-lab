# S2 첫 선형 adjoint의 Windows 확인

2026-10-15. 실제 Pro 반환의 [Linux 수용 기록](ACCEPTANCE_RESULTS.md)과 구별하는 Codex/Sol의 Windows 실행 기록이다. Pro는 핵심 수치·예제·시험을 작성했고 root는 공통 통합과 Windows 작업 디렉터리 처리를 교정했다. Sol은 전용 소스 이식, 독립 검사의 범위 사전검사와 시험 호환, 아래 실행 확인을 맡았다. 전체 S2/B5/B6 또는 공학적 승인이 아니다.

기존 Windows Python 3.12.14, NumPy 2.3.5, SciPy 1.17.0, scikit-fem 12.0.2를 그대로 사용했다. 설치·공급자·원격 CI 호출은 없었다. 공개 `examples.s2_mdo_adjoint --case adjoint`의 4×4 P1 메시(25절점, 자유 9/구속 16), 사전 고정 방향/간격/기준, 예산 80을 유지했다. 실행 제한 180초, cold 제한 180초, 외부 `native_check` 제한 300초도 두 실행에서 같았다.

## 실제 결과와 원 실패

첫 `actual-adjoint-01`은 primal 1회 성공 뒤 adjoint의 273문자 Windows cwd에서 WinError 267로 시작에 실패했다. 원 FAILED/STOPPED_AFTER_FAILURE와 로그를 보존했다. 이 실패를 새 프로세스에서 계산·adjoint·mapping 0회로 읽었고 소유 Job은 `job_empty`였다. timeout이나 수치 실패를 성공으로 바꾼 것이 아니다.

Root가 기존 실행기에 선택적 working_directory를 더하고, Windows scikit-fem 작업만 기존 Python 실행 파일 부모의 짧은 실제 디렉터리를 cwd로 사용하도록 교정했다. script/input/output·캡처는 절대경로와 원 native 폴더에 보존한다. Linux·기존 호출의 기본 경로는 유지하며 숫자나 알고리즘을 바꾸지 않았다. 원 긴 경로의 작은 소유 프로세스 검사는 root가 별도로 수행했다. 이 cwd 제약은 [Microsoft SetCurrentDirectory 문서](https://learn.microsoft.com/en-us/windows/win32/api/winbase/nf-winbase-setcurrentdirectory)의 MAX_PATH 초과 시 CreateProcessW 실패 안내와도 일치한다.

같은 깊이의 새 `actual-adjoint-02`는 다음 결과로 완료했다.

| 항목 | 실제 관측 |
|---|---|
| 실행 | SUCCEEDED / CONVERGED, 실제 수치 구간 30.846초. 같은 프로세스 원자료 조회와 별도 cold까지 포함한 외부 실행 106.71초, 종료 0 / `job_empty` |
| 목적 | 평균온도 `301.7129306573906 → 300.42823266434755 K`, 최종 k=40 W/(m K), q=5000.000000000002 W/m³ |
| 계산 비용 | optimizer 4후보 + 독립 검사용 12후보. 실제 primal 16 + adjoint 4 = 20 dispatch/예산 80. 보관된 primal 사본은 추가 계산으로 세지 않음 |
| 실제 jac | objective 4, jacobian 4, constraint 5, constraint-jacobian 4 호출. adjoint 내부 FD 0, 재조립 0. SciPy에 실제 callable jac 전달 |
| 초기 물리 미분 | dmean/dk=`-0.08564653286952194`, dmean/dq=`0.00017129306573904348`, 각 원 입력 단위 보존 |
| 잔차 | 최대 primal 상대잔차 `3.6723768167142744e-16`, adjoint `5.451535468476335e-16` (기준 각각 1e-10) |
| 두 방향 독립 검사 | 중앙차분 불일치 `4.2629053759180024e-10`, `1.4387219193778833e-10`. 마지막 R1 차수 `1.98772/1.99386`, `2.00550/2.00275`; 모두 원 기준 PASS |
| 저장·cold | 같은 원 정의·후보·단계/adjoint 원입력·행렬 참조·Post 입력을 읽고 별도 프로세스 cold PASS. solve/adjoint/mapping 0회 |

원 retained 관측만 다시 읽는 기존 `tests.s2_taylor_evidence_probe`도 두 정상 방향 PASS와 부호 반전·1.1배 오염 FAIL을 원 기준에서 확인했다. 새 FE 계산은 없었고 종료 0 / `job_empty`였다.

## 사전검사와 기록 위치

독립 검사를 선택하고 초기점이 경계 가까이에 있으면 고정 ±CENTRAL_H/+TAYLOR_H 점이 범위를 벗어날 수 있다. Sol은 최종 initial_values를 사용해 모든 검사점을 첫 `_Evaluators`/dispatch 전에 기존 physical 변환과 같은 조건으로 검사하고 내부 초기값 선택 또는 독립 검사 해제를 안내하도록 교정했다. clip·간격/기준 완화는 없다. 상하한·explicit 초기값·Taylor만 범위 밖인 점·정상 내부점 등 순수 시험 8건은 통합 후에도 통과했다. metadata admission과 evaluator 진입을 명시 대역으로 사용한 시험이며 물리 실행 증거와 구별한다. 공통 configure/Check에는 verify_gradient·initial_values가 없으므로 이 검사는 최종 실행 준비 경계에 있다.

로컬 근거 루트는 `runs/product-development/20261015/pde-s2-windows/`다. `preflight-contract-01`, `preflight-integrated-02`, 원 실패 `actual-adjoint-01`, 성공 `actual-adjoint-02/process`, 원 자료 `actual-adjoint-02/한글 결과/s2-adjoint-J3575537c7b0c4cc6a301b5468908378a.json`, 계산 없는 독립 재검사 `taylor-retained-02`를 보존한다. 각 native receipt가 소유 프로세스 종료를 확인한다. 다른 사용자 프로세스는 종료하지 않았다.

## 후속 parent reader와 Qt 표시 확인

위 Windows02 수치 실행 뒤, 실패·미완료인 독립 검사나 실패·취소된 부모 최적화 아래의 원 성공 adjoint가 최적화에 사용 가능한 값으로 다시 표시되지 않도록 reader와 GUI를 교정했다. 원 값·단위·SUCCEEDED 상태를 보존하는 것과 최적화 사용 가능 판정은 구별한다.

Root의 `_workspace/delivery-numerical-pde/s2-parent-admission-reader-02/`는 부모 SUCCEEDED/FAILED/CANCELLED와 독립 검사 None/PASS/FAIL/INCOMPLETE를 조합한 12개 controlled retained-reader 반례다. catalog·composite·원 adjoint attempt에 같은 부모 판정이 전달되고 원 자료가 유지됨을 확인했다. 실제 raw child를 읽었지만 새 물리 계산은 없었다.

별도 GUI 담당은 controlled API를 통해 실제 Windows Qt 창을 열어 표시를 확인했다. 초기 11개 검사 중 10개는 실제 Qt reader 표시 반례이고 1개는 기존 AST 표시 경계 검사다. PASS/FAIL/INCOMPLETE/기존 미검사 상태를 1180×820과 850×700에서 표시했다. 부모 실행 상태 연결 뒤에는 FAILED/CANCELLED 부모 아래의 성공 후보·adjoint 두 반례만 추가 확인했고 원 값·단위·자료를 그대로 유지하며 최적화 사용 불가를 표시했다. 새로 확인한 두 창은 `_workspace/delivery-numerical-pde/s2-gradient-admission-ui/parent-after/failed-parent-{1180,850}.png`, 상세 결과는 같은 폴더의 `RESULTS.md`에 있다. 소유 창·Job은 종료됐다.

Astra는 최종 소스·위 사진·Windows02 원 파일을 읽어 이 범위의 추가 차단을 찾지 않았다. 이 검토와 controlled Qt 확인은 새 FE/adjoint/Taylor 실행이나 보존 owner 전체 검증, OS 입력, 전체 GUI 사용자 작업의 수용으로 합산하지 않는다.

이번 확인에는 120-dispatch 비선형 MDO의 Windows 재실행, 전체 실패/취소 campaign, native ParaView와 MCP stdio를 포함하지 않았다. 실제 수치 실행은 위 선형 예제 범위이며 후속 reader·Qt 표시는 별도 근거다. 일반 nonlinear/coupled/shape/transient total adjoint와 engineering qualification은 미완료/UNKNOWN이다.
