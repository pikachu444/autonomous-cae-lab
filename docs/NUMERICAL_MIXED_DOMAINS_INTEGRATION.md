# 적용·검증 경계 — Numerical mixed domains

요청 PRO-NUMERICAL-MIXED-DOMAINS-20261015-01. 원문 REQUEST-R1이 ZIP 내부 초기 요청보다 우선한다.

## 정확한 적용 기준

main `ec502f3cdfa24e0b09cf1af672e2b4417d98bfb9`, pinned fixture_design `3e48bf6138f495299f45b1af254bfb4aaff307b8`.
첨부 publicsources.zip SHA256 `7671b7706354dc26ba87dc53ee583582bbfc4827763078ff3bdf11a44f9e590d`를 확인했고, SOURCE_FILES의 2,212개 소스 파일 해시를 대조했다. 다른 팀 working tree를 읽거나 교체한 결과가 아니다.

전용 추가 파일은 `files/` 아래에 있다. 기존 공통 파일은 **integration.patch hunk만** 넣었다. 전체 기존 파일 사본은 넣지 않았다. `MANIFEST.json`은 각 작성 파일의 기준/최종 byte hash와 길이, 줄바꿈 정규화 hash를 구분한다. 기준 소스의 혼합 CRLF/LF를 전체 정규화하지 않고 변경하지 않은 줄은 byte 단위로 유지했다.

적용 순서는 (1) 현재 소스와 manifest를 대조하고 전용 새 파일을 추가, (2) root가 15개 공통 파일의 hunk를 검토/적용, (3) 집중 검사, (4) Sol GUI의 typed 필드 보존과 Windows 확인이다. 정확한 첨부 기준 사본에서는 다음 명령으로 확인할 수 있다.

```text
git apply --check integration.patch
git apply integration.patch
python -m pytest -q tests/test_variable_domains_mixed.py tests/test_numerical_mixed_execution.py tests/test_numerical_mixed_owners.py tests/test_numerical_mixed_analysis_regression.py
```

현재 main에 후속 변경이 있다면 파일을 되돌리거나 전체 덮어쓰지 않는다. baseline hash가 다르면 hunk를 현재 변경과 대조해 병합해야 한다. 다른 팀 변경이 없는 깨끗한 ec502f3 사본에 패치를 적용해 최종 해시와 집중 검사를 다시 대조한 기록은 validation에 있다. 패치 자체는 실행 승인·공학 승인이 아니다.

## 공통 hunk의 목적

`numerical.py`: 기존 entry point에 typed 변수·후보·retained capsule 연결, 기존 예산/실패/취소/응답 해석 유지, 방법 admission만 추가. fit_model의 canonical inclusion/mask/provenance 부분은 수정하지 않는다.

`optimizers/scipy_de.py`: numerical target의 공개 integrality, finite 초기 집단, exact cache 통계. CAD/registry 대상의 기존 continuous/PASS 경계는 유지.

`dimensioned_models.py`, `model_parameters.py`, `adapters/dimensioned_ode.py`, `adapters/native_evaluation.py`: advertised ODE enum, 실제 setter와 기존 위치·모델 검증, 실제 입력 receipt와 solver_method 기록. 다른 설정 필드를 허용하는 임의 경로 API는 추가하지 않는다.

`pde_candidate.py`, `domain_candidate.py`: 보존된 full typed 값의 순수 검증과 실제 binding 확인. source·owner·CAS·C2 보호를 대체하지 않는다.

`evaluation.py`: 기존 결과 writer에서 typed 선언/값/choice/binding을 JSON 그대로 보존. 응답 배열 writer/store를 새로 만들지 않는다.

`evaluation_definition.py`: 완료된 실제 ndarray stage 결과를 기존 read_result로 읽는 4줄의 연결만 추가. 원래 live ndarray를 canonical_hash하려던 실패를 피한다. 재계산·재매핑·반복 MDO 교정은 아니다.

`assist/experts.py`, `numerical_document.py`, `research_operations.py`, `workbench.py`: 같은 schema/의미와 unavailable draft, exact retained export/new execution 인수, 기존 C2 backend_binding identity 연결. 새 registry/owner는 없다.

`optimizers/campaign_analysis.py`: 기존 continuous 회귀에 mixed 변수의 코드가 숫자로 흘러들지 않도록 직접 호출 경계에서도 명시 차단.

Numerical C2의 `numerical_candidate_evidence.py`, `numerical_candidate_detail.py`와 saved-input publication hook는 byte 그대로 보존한다. 두 파일의 API_MAP hash는 LF 정규화 hash이며 첨부 raw bytes는 CRLF다. 둘 다 manifest의 protected 항목에 구분해 기록했다. Data compiler/consumer, GUI, CURRENT_STATE/PRODUCT_PLAN/CODEX_WORKFLOW, 다른 팀 파일과 pinned upstream은 수정하지 않았다.

## 검증을 합산하지 않는 기준

집중 검사 76개에는 bounded AST/DAG·단위·실패, 실제 SciPy DE 직렬/배치/process, exhaustive algebra reference, 실제 ODE 24조합 및 실제 ODE DE, 실제 owner/JobManager, relocated cold edit/resave/세 번째 process, Evaluation stage, Material/Simulation 제어 evaluator 연결, 기존 continuous 분석 소비자 대조가 들어 있다. Windows native 성공을 뜻하지 않는다.

기존 continuous/optimizer/model_parameters/pde_candidate/workbench/research/campaign 분석 회귀는 별도 기록이다. 관련 PDE HTTP/owner 검사와 Evaluation·C2 경계도 별도 로그다. C2의 전체 51 node를 5묶음으로 실행해 통과했다. 한 번에 실행한 로그는 외부 실행 시간 제한으로 끝까지 완료되지 않았으므로 그 실행을 통과로 세지 않았다.

기존 `test_domain_candidate.py`는 원본과 최종 모두 20 통과/4 실패다. 네 실패는 fit 후보의 C2 보존 근거를 준비하지 않은 exact/missing/changed/changed_holdout 테스트가 기존 evidence gate에서 먼저 차단되는 현상이다. 해당 gate나 기존 검사를 통과시키기 위해 기준을 낮추지 않았다. 처음 --maxfail=3 검사에서 발견한 수보다 전체 대조의 실패 수가 하나 더 많다.

원래 예제 max_step=0.02 s에서 한 BDF 조합이 명시한 기준 비교를 넘은 기록도 남겼다. 허용 오차를 늘린 것이 아니라 입력의 max_step를 0.005 s로 줄이고 네 방법 전체를 다시 대조했다. 통과 결과는 이 **최종 입력**에 한정한다.

NOT_RUN: Windows Python/GUI, PySide6 조작, FELUPE 계산, native FreeCAD/Gmsh/다른 FE solver, 전체 HTTP 기능 캠페인, 최신 main 통합 및 Astra 독립 검토. 일부 실제 HTTP 회귀의 통과와 full HTTP 제품 수용은 다르다. FN-20-01 전체 GUI·행/점 최종 선택 수용, B5.2/UQ 확장, B5.4 adjoint, B5.5 local surrogate, B5.6 반복 MDO, B6 mesh/time mapping 전체 잔여를 완료로 세지 않는다.
