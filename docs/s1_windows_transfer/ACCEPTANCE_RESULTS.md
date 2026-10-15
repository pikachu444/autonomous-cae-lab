# 실제 검사 기록과 남은 수용 조건

2026-10-15 작성 환경: Linux, Python 3.13.5, NumPy 2.3.5, SciPy 1.17.0,
pytest 9.0.2. scikit-fem/PySide6 없음. Windows/FreeCAD/ParaView를 실행하지 않았다.
실제 파일 확인·계산·시험 대역·소스 작성·미실행을 구분한다. **S1 전체 수용 미완료**다.

## 실행 명령과 원 관측

### 새 S1 검사의 마지막 통합 실행

```text
python -m pytest -q tests/test_s1_p1_temperature.py tests/test_s1_owner_transfer.py tests/test_s1_gui.py tests/test_s1_installed_spatial.py -rs --tb=short
53 passed, 8 skipped
```

40개는 topology/보간/clock/온도 의미/VTU writer 계약과 실제 자식 프로세스의 frozen import 격리 검사이다.
13개는 실제 HTTP/owner/store/CLI/read API와 명시적 수치 시험 대역을 연결한 검사이다.
성공한 FE 계산 결과로 표시하지 않는다. 7개 실제 scikit-fem 검사는 의존성 부재로
NOT_RUN이고 Qt test module은 PySide6 부재로 NOT_RUN이다. 정확한 원 출력은
`evidence/pytest-s1-final.txt`; 깨끗한 패치 적용 후 재검사는 별도 `clean-*` 기록이다.
같은 검사를 재실행한 횟수를 새 통과 개수에 더하지 않는다.

### 기존 국소 회귀

```text
python -m pytest -q tests/test_dimensioned_research.py tests/test_thermoelastic_stages.py tests/test_evaluation_candidates.py tests/test_evaluation_mapping_lifetime.py tests/test_connected_evaluation_study.py tests/test_research_constitutive_transfer.py --tb=short
52 passed, 5 skipped

python -m pytest -q tests/test_pde_documents.py tests/test_pde_response_fields.py tests/test_pde_post_metadata.py tests/test_research_transfer_window.py tests/test_transfer_inspection_retry_ui.py tests/test_evaluation_window.py -rs --tb=short
94 passed, 2 failed, 3 skipped
```

실패 2건은 `test_generated_pde_metadata_opens_saves_and_restores_exact_clock[False/True]`다.
`apps/desktop_post/external.py:456`에서 시험 대역 `Native.HideUnusedScalarBars`가 없다는
AttributeError였다. 해당 제품/시험 파일은 이번에 변경하지 않았다. 첨부 원본 기준에서
`python -m pytest -q tests/test_pde_post_metadata.py -rs --tb=short`를 따로 실행해
**동일 2 failed, 1 passed**를 재현했다. 원본과 변경본의 두 파일 SHA256도 동일하다.
이를 수정하거나 제외하여 전체 green으로 표시하지 않는다. 실제 ParaView의 실패가 아니라
현재 baseline의 이 시험 경로 실패이며 실제 native 동작은 미확인이다.

중복 재실행을 제외한 위 세 실행 결과는 총 **199 passed, 2 failed, 16 skipped**다.
이 수치는 완성된 제품/물리 수용 항목 개수가 아니다. 이전 작성 중 테스트 연결 오타로
실패한 초기 owner 로그도 삭제하지 않고 보존했다. 마지막 실행과 구분한다.

### 실제 worker 및 실제 공개 예제: 실패

비대역 `thermal.scikit_fem.rectangle` worker를 기존 프로세스 supervisor로 실행했다.
`PackageNotFoundError`로 자식 return_code=1, FAILED_EXECUTION,
cleanup_pending=false를 기록하고 정확한 소유 PID를 reap했다. 가짜 field나 대체 solver가 없다.
원 stdout/stderr/input/source snapshot/실행 기록은 `evidence/actual-worker-missing-package/`에 있다.

```text
python -m examples.s1_windows_transfer --workspace "/mnt/data/s1-evidence/public example 한글" --case uniform
execution_status: FAILED
physics: NOT_RUN_OR_FAILED
native_ParaView: NOT_RUN
qualification: UNKNOWN
cold_read: PASS; new_process: true; solve_calls: 0; mapping_calls: 0
exit code: 2
```

이는 실제 FE 성공 증거가 아니다. 원 계산 실패를 저장하고 원 owner를 종료한 다음
새 Python 프로세스에서 그 실패 결과를 계산 0회로 재열었다는 증거다. 별도 성공/전달/실패
재열기 검사는 수치 시험 대역을 사용한다. 원 경로가 들어 있는 evidence store는 감사용
원자료이지 위치 변경까지 검증한 portable project 패키지가 아니다.

## 원 ACCEPTANCE.md별 판정

| ID | 이번 관측 / 상태 | 남은 것 |
|---|---|---|
| A01 | 실제 조립/solver 코드 및 두 메시·계수/BC/domain 수정 검사 작성. 실제 worker는 missing dependency FAILED | 실제 FE DOF/잔차/독립 norm, Windows 실행 NOT_RUN |
| A02 | invalid AST/차원 draft 저장 및 Check 0, 수정 owner 경로 PASS | 수정한 식/계수의 실제 FE 결과 변화 NOT_RUN |
| A03 | 6→12절점 상수 P1 보간·원 hash/values/weights 보존 PASS (계약 시험) | 실제 FE producer→receiver solve NOT_RUN |
| A04 | sparse/reordered IDs와 실제 연결로 affine 보간 PASS, 관측 max error 5.68e-14K ≤1e-10K | 실제 FE로 만든 affine 원장 검증 NOT_RUN |
| A05 | hole/외부/mask/NaN/퇴화/메타/hash 반례 PASS. 실제 owner에선 시험 대역 producer 후 수신 제출 0과 실패 보존 PASS | 실제 FE 통합 캠페인 NOT_RUN |
| A06 | 서로 다른 2개 원 topology의 0/2초→1초 0.5/0.5 및 bracket/order/origin/누락 반례 PASS | 실제 heat snapshot 생성 NOT_RUN; transient physics 없음 |
| A07 | K/°C와 ΔK/Δ°C, Tref provenance/변경 거절/중복 차감 방지 계약 PASS | 실제 0.00069m/free-expansion/응력 검증 NOT_RUN |
| A08 | 실제 writer XML, 원 owner의 Post source 등록·원 필드 read PASS (수치 시험 대역) | 실제 탄성 계산/Qt 선택/ParaView native NOT_RUN |
| A09 | 실제 Python/HTTP/CLI, 얇은 MCP 함수의 기존 HTTP 호출, Plan 생성 0 PASS | MCP SDK/stdio, 실제 Qt flow NOT_RUN |
| A10 | 수신/전달 실패와 부분 원결과, prefix exact reuse/drift 거절, receipt corruption 거절 PASS | 실제 FE 수신 실패/수렴 캠페인 NOT_RUN |
| A11 | late producer 취소 및 mapping 직후 취소에서 후속 제출 0 PASS (시험 대역). 실제 missing-dep child cleanup PASS | 실제 FE 중 취소/timeout/native 창 캠페인 NOT_RUN |
| A12 | 원 owner 종료→새 Python 프로세스 exact 정의/결과/전달/Post read 0 PASS (대역 성공/실패). 비대역 의존성 실패 cold read도 PASS | 실제 FE 성공의 Windows cold read NOT_RUN |
| A13 | 위 회귀의 통과와 기존 exact/Picard/lag/DefinitionFactory 경계 유지. baseline의 Post 시험 실패 2건 재현 | Qt/native skip 및 원 실패 유지; 전체 regression green 아님 |
| A14 | 기존 Qt에 mapping/source/receiver/시각/SI selector 연결 코드 및 normal/narrow 렌더 검사 작성 | PySide6 없음: 렌더 0, 사용성/한국어/focus/selection 실관측 NOT_RUN |

## 원 허용값 보존

원 thermoelastic reference 파일은 변경하지 않았다. 기본 relative residual ≤1e-10,
free-expansion error ≤1e-10m, uniform spread ≤1e-8K, 원 grid rtol=1e-12/atol=1e-14,
온도 0..5000K와 mesh bounds를 사용한다. dimensioned weak 기본 residual ≤1e-9다.
새 mapping 재현 기준은 요청의 1e-10K이다. 기존 Newton/benchmark tolerance를 완화하지 않았다.
새 경로에서 기존 nonlinear Newton나 과도 적분 benchmark를 수행했다고 표시하지 않는다.

## GUI와 독립 검토

첨부 desktop skill의 QT-PANELS/QT-ACCESS를 적용해 일반/좁은 창의 레이아웃, 동일 modal
편집 중 늦은 callback 보호, 위젯 이름/키보드 focus 경계를 코드에 반영했다.
VIS-TYPE에 따라 단위와 stage 이름을 주 표시로 하고 refs를 보조 정보로 옮겼다.
PV-VIEW에 따라 원 snapshot 선택, mapped 값, 실제 received 값을 분리하고 display 선택이
저장 입력을 바꾸지 않도록 기존 owner를 사용했다. 이는 **설계 적용 내용**이며 실제 렌더
관측이 아니다. 테스트가 성공할 때만 원 데이터로 normal/narrow PNG를 생성한다.
가짜 스크린샷은 제공하지 않았다. Sol의 GUI 연결 검수/Astra 독립 검토를 받았다고 주장하지 않는다.

S2 MDO/첫 실제 adjoint, 현재 main b2e359d 통합, Windows 실행은 이번 통과 주장이 아니다.

## 마지막 import 격리 교정

설치형 Python에서 `plugins` namespace/regular-package 우선순위로 외부 설치 경로를
선택할 여지를 소스 검토에서 발견했다. 원 `plugins/thermoelastic/__init__.py`도 동결하고
worker의 `plugins` 탐색을 해당 사본으로 한정했다. 실제 import된 제품 모듈 경로/hash를
검사해 `import_identity.json`에 기록한다. 자식 Python에 의도적으로 충돌하는 외부
`plugins`를 제공한 뒤 실제 계산 직전에 강제 종료하는 검사에서 원 보존 사본만 선택됐다.
이 검사는 FE 조립 성공이 아니다. 교정 전 원 worker 의존성 실패/초기 clean 로그는
보존하고, 최종 패치 적용 결과는 `clean-final-*` 로그와 구분한다.
