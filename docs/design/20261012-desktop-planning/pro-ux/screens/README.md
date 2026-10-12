# Editable Qt screen states

Each SVG is a 1440×900 native Qt client view. Edit screen_states.json and regenerate to change a state.

| State | Engineering task | Next |
|---|---|---|
| [Sketch dimensions](cad-sketch.svg) | 선 생성 → 선 좌표/직사각형 치수 수정 → 구속 → Pad | cad-features |
| [Pad and pocket](cad-features.svg) | 폭·높이·두께와 관통 구멍을 편집하여 형상을 확인 | cad-assembly, cad-mesh |
| [Assembly instances](cad-assembly.svg) | 인스턴스와 joint를 선택하고 해당 부품을 이동 | cad-motion |
| [Joint pose](cad-motion.svg) | 선택 부품의 상대 자세 미리보기 → Use pose 또는 Restore | cad-mesh |
| [Mesh quality](cad-mesh.svg) | 요소 유형/크기 → 합성 메시 → 불량 요소 선택 → 재생성 | cad-conditions |
| [Support and load](cad-conditions.svg) | 선택 면에 고정·변위·힘·압력을 지정하고 Apply/Cancel | cad-contact, simulation-implicit |
| [Contact surfaces](cad-contact.svg) | Set A/B와 접촉법칙·마찰·간극을 편집 | simulation-implicit |
| [Implicit analysis](simulation-implicit.svg) | 저장 형상 업데이트 → 솔버/단계/조건 → Run analysis | runner-convergence |
| [Impact initial conditions](simulation-explicit.svg) | 충돌 시간 증분·초기 속도·에너지 출력을 편집 | runner-cancel |
| [Failure output](simulation-failure.svg) | 계면 강도·파괴에너지·damage를 지정하고 출력 선택 | runner-convergence |
| [Correct time increment](simulation-invalid-step.svg) | 잘못된 입력의 정확한 셀을 고친 다음 재검토 | simulation-implicit |
| [Thermal plate](thermal-domain.svg) | CAD 없이 독립 판 영역·온도 경계·열 출력을 편집 | evaluation-transfer |
| [Thermal expansion](thermoelastic-field.svg) | 정확한 thermoelastic 모델의 기준 온도·열팽창계수 | evaluation-transfer |
| [Job convergence](runner-convergence.svg) | 선택 작업의 진행·잔차·입력·로그를 확인 | post-field |
| [Cancel and reconnect](runner-cancel.svg) | 취소 요청과 종료 수신을 구분하고 같은 작업으로 재연결 | runner-convergence |
| [Result field and frame](post-field.svg) | 배열·association·실제 프레임·범례·곡선·측정값 연결 | post-clip, post-gauge |
| [Clip plane](post-clip.svg) | Clip의 축과 위치를 지정하고 Apply/Reset | post-gauge |
| [Plot along gauge](post-line.svg) | 선의 시작/끝과 표본 수를 지정해 곡선 대상 변경 | post-gauge |
| [Two-point measurement](post-gauge.svg) | 두 점·방향 선택 → 측정표 → Numerical 응답 등록 | numerical-moo |
| [Compare exact results](post-compare.svg) | A/B 결과의 원 형상과 동일 프레임을 나란히 비교 | numerical-moo |
| [Unavailable frame](post-unavailable.svg) | 존재하지 않는 프레임의 값·곡선을 제공하지 않고 선택 수정 | post-field |
| [Objectives and constraints](numerical-moo.svg) | 변수·목표·제약과 후보를 비교하고 비지배 feasible 점 확인 | candidate-partial-save |
| [DOE inputs](numerical-doe.svg) | 설계행렬과 응답·효과 판단 | result-doe |
| [DOE result](result-doe.svg) | 설계행렬과 응답·효과 판단 → 선택 근거를 Expert/Study로 전달 | expert-followup, study-judgment |
| [Inverse inputs](numerical-inverse.svg) | 관측 source/mask/weight/잔차와 독립 holdout | result-inverse |
| [Inverse result](result-inverse.svg) | 관측 source/mask/weight/잔차와 독립 holdout → 선택 근거를 Expert/Study로 전달 | expert-followup, study-judgment |
| [Optimization inputs](numerical-optimization.svg) | 후보 이력·목적함수·제약과 실패를 비교 | result-optimization |
| [Optimization result](result-optimization.svg) | 후보 이력·목적함수·제약과 실패를 비교 → 선택 근거를 Expert/Study로 전달 | expert-followup, study-judgment |
| [Sobol sensitivity inputs](numerical-sobol.svg) | A/B/교차 행렬·first/total·불확실성과 수렴 | result-sobol |
| [Sobol sensitivity result](result-sobol.svg) | A/B/교차 행렬·first/total·불확실성과 수렴 → 선택 근거를 Expert/Study로 전달 | expert-followup, study-judgment |
| [UQ inputs](numerical-uq.svg) | 분포·단위·상관과 분위수·실패 사건 | result-uq |
| [UQ result](result-uq.svg) | 분포·단위·상관과 분위수·실패 사건 → 선택 근거를 Expert/Study로 전달 | expert-followup, study-judgment |
| [RBF surrogate inputs](numerical-surrogate.svg) | 학습/검증 분리·예측 support·외삽 불가 | result-surrogate |
| [RBF surrogate result](result-surrogate.svg) | 학습/검증 분리·예측 support·외삽 불가 → 선택 근거를 Expert/Study로 전달 | expert-followup, study-judgment |
| [MDO inputs](numerical-mdo.svg) | 기존 Evaluation의 discipline/transfer/반복 | result-mdo |
| [MDO result](result-mdo.svg) | 기존 Evaluation의 discipline/transfer/반복 → 선택 근거를 Expert/Study로 전달 | expert-followup, study-judgment |
| [Apply candidate](candidate-partial-save.svg) | CAD와 Material에 명시 Apply/각 Save·실패한 쪽 Retry | cad-features, material-fit |
| [Measurement workbook](data-workbook.svg) | 열명·단위·역할·수식과 8개 ID 선택/curve/mask | material-fit, data-calibration |
| [Calibration original](data-calibration.svg) | 정확 Calibration 원문·locator·유효 범위를 열기 | data-workbook |
| [Calibrate material](material-fit.svg) | 왼쪽 시험/계수와 오른쪽 관측·예측 curve, 하단 output | numerical-inverse |
| [Constitutive history](material-history.svg) | J2 계수·하중 이력·초기 state를 독립 편집 | numerical-inverse |
| [Locate original test](material-repair.svg) | 저장된 r19의 missing test를 locate; 동일/변경/취소 구분 | material-fit |
| [Field and boundary](pde-equation.svg) | 같은 field/domain/mesh에서 각 경계 type/value 독립 Apply | pde-weak-form |
| [Weak form](pde-weak-form.svg) | test/trial/domain/적분식을 편집하는 확장 정의 | pde-ode |
| [ODE state and time](pde-ode.svg) | state/RHS/IC/time 정의와 별도 합성 응답 curve | numerical-doe |
| [Thermal field transfer](evaluation-transfer.svg) | Heat → Expand 단계·K/POINTS/동일mesh 전달 확인 | evaluation-coupling |
| [Coupling definition](evaluation-coupling.svg) | 반복법·원래 허용치·반복 상한과 각 stage 열기 | numerical-mdo |
| [Co-STORM discussion](expert-discussion.svg) | 논점 선택·다자 발언 예시·reply/evidence·하단 개입 | expert-models, numerical-doe |
| [Role models](expert-models.svg) | 미설정 / 기존 OAuth / 기존 local endpoint와 역할 모델 연결 | expert-discussion |
| [Discuss selected result](expert-followup.svg) | 동일 DOE 결과의 선택 행을 근거로 사용자 후속 질문 | study-judgment |
| [Competing hypotheses](study-judgment.svg) | 가설·지지/반박 근거와 명시 judgment·다음 연구 | numerical-doe, expert-discussion |
| [Research connections](workbench-links.svg) | 노드/port/연결을 선택하면 정확한 기존 owner로 이동 | cad-sketch, expert-discussion |
