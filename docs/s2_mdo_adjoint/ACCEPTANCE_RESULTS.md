# S2 실제 수용 기록

기준 source 5ee81c544093b6feb78fc874fd09be380d47f223, fixture3e48.
첨부509파일은 원 manifest의 bytes/SHA256/Git blob 전부 일치. wheel178478B/CRC/SHA 일치 후
오프라인 설치. 실제 실행은 Linux Python3.13.5/NumPy2.3.5/SciPy1.17.0/scikit-fem12.0.2.
양성 FE는 계산 대역이 아니다. 일부 실패 관문 검사만 실제 생산된 필드를 의도적으로 훼손한 반례다.

## 실제 수치 결과

| 경로 | 실제 관측 |
|---|---|
| 선형 primal/adjoint | 25절점, 자유9/구속16. 실제 원 CSR transpose solve. 첫 검사 adjoint 상대잔차 약4.58e-16. 최종 예제16개 primal의 최대 상대잔차3.6724e-16. |
| 비영 미분 | 최종 초기점 dmean/dk=-0.08564653286952194 K/(W/(m*K)), dmean/dq=0.00017129306573904348 K/(W/m^3). 별도 T0 검사는 직접0.4375 + 경계0.5625 ≈1. Celsius offset도 독립 검사. |
| 독립 Taylor | p1/p2 중앙 오차4.2629e-10/1.4387e-10. 마지막 두 R1 차수 p1=1.98772,1.99386; p2=2.00550,2.00275. 두 방향 모두 비영·roundoff 위에서 2차. sign 반전/1.1배 오염은 같은 한계에서 FAIL. |
| 실제 SLSQP | 평균온도301.7129306573906→300.42823266434755 K. 최종 k40,q5000.000000000001. CONVERGED. optimizer4후보 + 독립검사12primal, adjoint4, 총20 actual dispatch/예산80. callable objective4/jac4/constraint5/constraint-jac4; 외부 FD jac0. |
| 활성 제약 | 별도 실제 평균온도>=301 K 제약, 10scale의 정확 부호/gradient 보존과 positive multiplier·수렴을 확인. 초기 시험에서 누락됐던 constraint-gradient retention을 교정 후 실제 재검사 PASS. |
| 비선형 MDO | 기존 DE 10후보, 모두 실제 열·구조12stage=6Picard, 총120dispatch/예산200. SUCCEEDED이나 optimizer 종료는 MAX_GENERATIONS이며 최적성/DE 수렴으로 부르지 않는다. |
| MDO 응답 변화 | Tref293.15에서 mean337.5856696398144 K/최대변위0.0010267525599439555 m. 선택 Tref300.99943942075646에서 mean337.7445408158042 K/최대변위0.0008439264296843536 m. 최대 실제 stage 상대잔차1.4369e-15. |
| 실제 수렴식 | 초기 후보 마지막 L∞ 변화1.6968812e-7 K <=4.4693149e-6 K; 선택 후보1.6714057e-7 <=4.4728239e-6. 원 saved abs/rel/scale/max 유지. |
| 독립 direct 일치 | 실제 DE 선택 후보를 **원 saved definition hash**로 별도 direct Evaluation12stage 실행. response SHA와 initial_state SHA 모두 정확히 일치. |

## 요구별 관측

| 요구 | 현재 결과 / 근거 |
|---|---|
| S2-01 공유 입력 | PASS(core). 하나의 shared row, 단위/초기·범위/targets/실제 값 보존, Check0, 중복/충돌/unknown/단위 거절, 구형 binding 재실행. shared_admission+실제 MDO/direct 증거. |
| S2-02 실제 MDO | PASS(작은 공개 수치). actual-mdo-r01의10후보120stage와 independent-direct-mdo-r01. 최적성은 미확인/MAX_GENERATIONS. |
| S2-03 상태 격리 | PASS. actual_s2_tests의 a,b,a 및b,a 5회 실제 Picard, 초기해시/응답 동일·candidate폴더별 UUID·compiled 원본 불변. |
| S2-04 실패 | PASS(core). max1 별도반례 NOT_CONVERGED/응답없음/best없음, 실제 producer뒤 mask/clock/topology 훼손 receiver0, required 관문. legal q1e8의 물리범위 거절 원 unvalidated field 보존. q1e9 원입력범위거절0stage. prefix exact성공만 재사용·drift/partial-loop 거절. |
| S2-05 adjoint | PASS(선언된 선형). 원CSR/free DOF/원reduction, 직접/경계/잔차항·단위·sourcepins와 transpose1/FD0. nonlinear/shape/coupled total은 NOT_IMPLEMENTED. |
| S2-06 독립 검증 | PASS. 최종 실제 SLSQP의12독립primal/두방향/Taylor 원값·refs, 별도 finite-difference k/q/T0 및 sign/scale 오염검사. constants첫캡처와 최종동일. |
| S2-07 gradient 소비 | PASS(core/Python/HTTP). 실제 SciPy callable jac 소비 및 활성제약. 실제 GUI 클릭 경로는 NOT_RUN. |
| S2-08 취소/예산 | PASS(소유 실행 검사). after-primal/during-adjoint/late-adjoint 취소; HTTP 실제RUNNING PID 관측 후 취소; primal보존/adj0 budget; 기존 단일경로2후보×2stage budget2 호환. 초기 외부도구 hard-timeout의 finally 확인불가는 별도 FAIL/UNKNOWN 보존. |
| S2-09 같은 API/UI | Python/HTTP/CLI saved owner/정의·후보/분야·미분·전달 읽기 PASS. 실제 Post 데이터 등록·hash 확인 PASS. Qt/Windows/ParaView native 표시·MCP stdio·focus/selection/좁은창 수용은 NOT_RUN. GUI 소스와 원 수정용 테스트는 포함. |
| S2-10 saved cold | PASS(현재 읽기). 성공adjoint/MDO, 원 PARTIAL_FAILURE(nonconvergence), CANCELLED 모두 새 process/owner에서 계산·adjoint·mapping0. missing/corrupt system 거절. MDO최초90s읽기는 TIMEOUT; cold-only400s한계 재시도 PASS(188.53s), 원 timeout 보존. |
| S2-11 국소 회귀 | 기존 영향106PASS. 새 shared/뷰 데이터33PASS, Qt2SKIP. 실제FE20항은 각 항의 최종 실행에서 PASS(전체를 한 번에 반복하지 않음). 원 collector 누락 파일 때문에 못 읽은2연결 suite는 NOT_RUN. |

pytest 검사의 최종 항목 기준은 33 +20 +106 =159 PASS와 Qt2SKIP이다. API 예제·CLI·cold·direct·Taylor
별도 probe는 이 pytest 수에 중복 합산하지 않는다. 이후 clean apply 검사도 중복 합산하지 않는다.

## 실행 로그 지도와 보존된 실패

`logs/final-pure-ui-data-r04`=33PASS/2SKIP. `local-regression-r02`=106PASS.
`actual-s2-tests-r01`=12PASS/4FAIL을 원문으로 유지한다. 세 반례는 시험 wrapper의 artifact 상대경로가
잘못돼 producer 단계에서 먼저 실패했던 문제이며 원 FE 대역이 아니다. 경로를 수정한 r02에서 receiver0
관문을 실제 확인했다. 남은 source1e9는 기존 입력상한1e8 밖이므로 before-worker 거절이 맞았다.
legal1e8 physical rejection과 originalout-of-range0stage를 분리하고 실제 원 unvalidated field 보존을
교정한 r03에서 확인했다. r03 활성제약 시험은 소비된 gradient 보존 필드 누락을 찾아 FAIL했고 실제
교정 뒤 `active-constraint-retention-r04`는 PASS. 실패 로그를 성공로그로 덮지 않았다.

`final-owner-adjoint-r08`=현재 HTTP Plan/직접 Jac 소비/저장/newprocess cold 모두PASS.
`actual-mdo-r01`=계산 성공 후 cold90s timeout; `mdo-cold-only-r02`=동일 원 자료 읽기만PASS.
`owner-nonconvergence-r01`, `owner-cancel-r01`은 실제 의도된 원 실패/취소를 보존한 뒤 probe 기록의
옛 key 이름 때문에 cold verifier가 실패했다. 기록을 변형하거나 재계산하지 않고 reader가 옛 기록 key를
해석하게 한 cold-only-r02 두 실행은PASS. 각각 원 PARTIAL_FAILURE/CANCELLED 상태를 그대로 읽었다.
`independent-taylor-audit-r01`, `mapped-candidate-read-r02`, `independent-direct-mdo-r01`은PASS.
`cli-owner-…-r01`은 packet에 없는 caelab.__main__을 호출한 시험명령 오류였고 제품 결함으로
조용히 덮지 않았다. 기존 console entrypoint caelab.cli:main을 실제 호출한 r02두건은PASS/계산0.

초기 actual-adjoint r01/r02는 schema/reduction, r03은 DE 전용 budget 옵션의 SLSQP 혼입을 찾아
계산 전 거절했다. root 최소 수정으로 처리했다. r04/r05는 실행 도구의 외부 hard-timeout이며 일부
finally 완료는 확인되지 않았고 소유 프로세스 잔류0 사후관측과 구분했다. r06의 원 취소/partial
결과도 보존한다. 성공/실패/timeouts의 실제 process receipts는 evidence/logs에 포함한다.
`local-regression-r01` collection error는 첨부에서 빠진 test_thermoelastic_stages 의존이다.
파일을 만들어 가짜 collector 성공으로 처리하지 않았다. PySide6설치 시도 실패도 원문 유지한다.

## 판정 경계

이 작성자의 Linux 수치/서비스 증거와 사용자가 전달한 기존 S1 Windows 증거는 별개다. 새로운 S2의
Windows/native/Qt를 실행했다고 합치지 않는다. 독립 Astra 검토·Sol 실제 렌더 검토·공학 qualification은
수행하지 않았다. 더 넓은 비선형/coupled/shape/transient adjoint와 제품 전체 B6/MDO는 여전히 열린 범위다.
