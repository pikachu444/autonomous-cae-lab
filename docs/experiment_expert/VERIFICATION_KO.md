# 실제 검사와 미실행 범위

요청 PRO-EXPERIMENT-EXPERT-20261015-02의 **이번 실행**만 기록한다. 전체 제품
인수, 실제 장비 인수, 수치/공학 승인, 다른 팀 C2 CAS 완료 기록이 아니다.
정확한 최종 실행 결과/환경/패치 적용 대조는 ZIP의 `verification/`에 포함한다.

## 검사한 실행 경로

| 경로 | 실제 실행한 부분 | 시험 대역/미실행 부분 |
|---|---|---|
| 입력/소유 확인 | 첨부 ZIP hash, manifest 442개 바이트/hash, 새 파일과 공유 hunk 분리 | 현재 main/미게시 작업 폴더를 읽었다는 주장 없음 |
| 공개 전파 | 실제 NumPy 선형대수, 기존 calibration/file_table, 명시 U/k/단위/상관/미확인 | 공개 CSV/교정 증빙은 합성 예제, 실제 센서 측정 아님 |
| Data 처리 기여 | 제공 C1 실제 processing/trace_sample, SG/보간/nearest/교정 application, 처리 개정 저장/재열기 | partial baseline의 빠진 owner hook은 테스트에서 명시 조합; C2 canonical 운반/CAS 미실행 |
| 최종점 수학 | 실제 finite difference/SVD, 고정/log/경계/rank-deficient/비매끄러움/실패/예산/취소 | 대부분 공개 analytic evaluator; 실제 FE/장비 모델 아님 |
| 지원 수치 평가 | 기존 `pde.scipy.ode` adapter/evaluator와 기본 허용치, 실제 5개 새 J 평가, 해석식 비교, 보존 artifact | 원 ODE 후보는 알려진 계수의 명시 보존 fixture. 원 ODE optimizer가 실행됐다는 주장 없음 |
| 실제 optimizer | 설치 SciPy robust LSQ와 DE가 공개 analytic evaluator를 실제 실행, 선택 최종점에서 일반 J 별도 생산 | 기존 native solver/Windows Qt optimizer 실행 아님 |
| Core 실행 | 기존 Workbench 메서드, DesktopLinks receipt, Numerical/Discussion/Data/Study/Report owner, 실제 JobManager | 첨부 baseline의 빠진 native Pre 때문에 전체 Workbench 생성 대신 테스트-only ServiceHost 조합 |
| Numerical C1 | 실제 candidate/detail/evidence 모듈의 저장·검증·read/success/failure gate | 실제 제공 CandidateDetailMixin와 owner를 테스트에서 조합. C2 PRESERVING/CAS 수용 아님 |
| 저장/재열기 | 기존 revision 자산 검증, 원 휘발 파일 삭제, 새 owner 인스턴스 읽기, 읽기 중 0 모델 호출 | 운영 Windows 새 앱 프로세스 cold reopen 아님 |
| FN30 | 기존 Discussion owner, 권한/자료 확인, vendored Co-STORM runner, saved journal/retry, cancel, Study/Report | provider 생성문장과 검색/prompt 직렬화가 시험 대역. 실제 계정/OAuth/provider 새 호출 0 |
| Qt | 실제 PySide6용 시험 코드와 새 창/공유 연결 syntax 확인 | PySide6 미설치로 Qt 테스트 module skip. Linux GUI/Windows GUI 모두 실행하지 않음 |

## 회귀의 주요 보호 조건

누락 상관을 독립으로 바꾸지 않는지, 확장 U의 k가 없을 때 UNKNOWN인지,
단위/PSD/대각 모순을 차단하는지, 원 output uncertainty를 덮지 않는지 검사한다.
같은 raw import의 공유 계수는 유지하되 숫자가 같은 서로 다른 채널의 교정을
합치지 않는다. signed 값 기여와 validity footprint가 섞이지 않는지 대조한다.

robust optimizer J를 재사용하지 않고 DE의 미보존 J를 성공으로 보지 않는다.
정확 최종 계수·변환·원 fit 관측/마스크/가중·evaluator를 보존하며 기존 rank
허용치를 유지한다. h/h2 불일치와 abs의 대칭 뾰족점은 판단 UNKNOWN이다.
원 fit holdout 실패·과거 실패 attempt를 나중 성공으로 채우지 않는다.

원 결과→명시 Plan 생성/실행 응답 유실을 주입해 같은 command ID/동결 payload로
재시도하고 하나의 Plan/job만 유지하는지 확인한다. stale generation을 자동
최신화해 미전송 입력을 덮는 경로가 없는지 검사한다.

Report는 일반 metadata_only 주소만이 아니라 실제 원값/기여/곡선/진단 배열을
보존한다. FN30은 같은 원 job의 부분 journal을 읽고 현재 budget으로 명시 retry,
미전송 의견 보존, malformed completion 제외, 자료 개정·권한 취소 차단을 확인한다.
큰 결과가 formatter에서 통째로 빠지는 현상은 실제 runner 경로에서 재현했고
새 시험 분석에 한정한 bounded summary와 원 ref 보존으로 교정했다.

## 최종 재현 명령

깨끗한 첨부 baseline 사본에 product/core/GUI 패치를 적용한 후:

```text
CAELAB_CONTRACT_ROOT=<첨부 references 절대경로> PYTHONPATH=. python -m pytest -q \
  tests/experiment_expert tests/test_experiment_identification.py tests/test_experiment_calibration.py \
  -k 'experiment_expert or distinguishes_local or unknown_robust or event_scalar or disjoint_fit or affine_voltage or acquisition_output or partially_provided'
```

최종 실행 **63 passed, 1 skipped, 6 deselected**. skip은 PySide6 모듈 1개다.
선택 해제된 6개를 통과로 세지 않는다. 신규 회귀와 기존 영향단위 순수 회귀를
선택한 명령이며 전체 benchmark를 반복한 수치가 아니다.

공개 파일 예제도 직접 실행했다:

```text
python examples/experiment_expert/analytic_uncertainty.py --output <존재하지 않는 결과 폴더>
```

원 출력 0.5, 2.5, 6.5, 8.5, 10.5 N에 대해 제공 불확실성 조건부 값 전파는
0.3, 0.31622776601683794, 0.42426406871192857, null, null N다.
마지막 두 표본은 원 제외 조건을 보존한다. 전체 측정 U는 UNKNOWN이다.
이 결과는 실제 센서 성능을 검증한 것이 아니다.

## root / Sol / Astra의 남은 실제 인수

현재 main/C2 통합 사본에서 hunk를 합친 뒤 native Qt 두 크기(980×720,
1440×900), Data 정확 선택/계수·공분산 편집/키보드/저장·닫기/미확정 재시도,
원창 변경 중 늦은 callback, 명시 취소를 확인해야 한다. C1 endpoint의 실제
HTTP 왕복, C2 canonical packet 운반 및 증빙 CAS, Windows 지원 evaluator의
기준 잔차 재현/차분 일관성은 해당 실제 통합본으로 확인한다.

실제 provider 호출과 장비 연결은 이번 요청에서 실행하지 않았다. 추가 비용,
새 provider fallback, 실제 장비 stop 확인, 신뢰구간·전역 유일성·공학 승인으로
이 테스트 결과를 확장하지 않는다.
