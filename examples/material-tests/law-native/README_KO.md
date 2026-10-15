# 공개 law-native 예제

모든 계수/입력은 공개 합성 자료이며 실측/회사 자료가 아니다. `inputs/`의 독립 expected는 실제 native 결과가 아니다. 기본 FE는 27절점·8 Hex8·64적분점·실제 내부 자유 DOF가 있는 작은 cube다.

`make_public_inputs.py --output <새 경로>`: DP 4protocol/Neo/SLS와 원 canonical9/refined17, 명시 point/FE 입력 및 독립 analytic expected를 생성한다. 입력 생성은 solver 실행이 아니다.

`point_fit_workflow.py --output <새 경로>`: 기존 Data/Numerical/Material owner에서 k0 fit 및 holdout/evidence/CAS/cold 경로를 실제 실행한다. E/nu/alpha/beta/H는 고정. 원 workspace와 실패도 보존한다.

`fe_workflow.py --output <새 경로>`: 실제 FELUPE 11.1.3가 있는 환경에서 세 법칙의 public FE를 기존 Simulation/JobManager로 명시 실행한다. `--input <law_freeze에서 받은 simulation_draft JSON>`는 saved Material→native assignment 입력을 사용한다. runner는 FE ACTUAL과 pair PASS를 둘 다 요구한다. no-runtime을 FE 성공으로 바꾸지 않는다.

각 실행은 `tools/law_native/owned_check.py --output <새 검사 경로> --timeout <상한 초> -- <Python> <위 script> ...`로 감싸며 내부 Workbench도 finally shutdown한다. 전체 Windows/native 명령과 정확한 출력 경로는 `docs/law-native/WINDOWS_KO.md`, 식/측도는 `EQUATIONS_KO.md`를 따른다.
