# 실제 검사 / 미실행 / 남은 관문

## 2026-10-15 Windows 통합 확인

아래는 Codex가 Pro 반환 전용56파일과 root 공통17 hunk를 현재 main에 연결한 뒤 별도로 수행한 기록이다. 뒤에 보존한 Pro의 Linux 검사·NOT_RUN 기록을 Windows 성공으로 바꿔 쓰지 않는다. 수치 kernel10파일과 DP/Neo/SLS 원 허용값은 반환 원문 그대로다.

기존 Windows runtime Python3.12.14/FELUPE11.1.3/PySide6.9.1을 사용했으며 새 설치는 없다. 모든 실행은 `scripts/native_check.py`의 새 output/owned Windows Job에 넣었고 정상·실패 모두 `job_empty` 종료를 확인했다.

| 실제 확인 | 기록과 범위 |
|---|---|
| DP·SLS point/독립 접선·전송 owner 회귀 | `runs/product-development/20261015/law-native-windows-small-01/`: 28 pass/1 fail. 실패는 테스트가 live `controller.lock`의 bytes를 읽으려던 Windows PermissionError다. 그 운영 lock의 inode/크기/mtime만 비교하고 다른 원파일은 계속 bytes 비교하도록 테스트를 교정했다. 해당 preview 재검사는 `law-native-windows-preview-02/`에서 1 pass다. 원 실패와 첫 경로 교정 실수도 보존한다. |
| 실제 FELUPE Neo-Hooke point·회전·physical9 접선 | 같은 small-01의 `test_actual_neo_energy_measure_rotation_and_independent_tangent`에서 실제 FELUPE와 독립 P/dP_dF/에너지 기준을 통과했다. |
| DP/Neo/SLS 실제 공간 FE와 같은 법칙 point pair | `law-native-windows-fe-01/workflow/workflow-receipt.json`: 공개 27절점/8Hex8, 각 요소 8적분점과 내부 자유 DOF의 실제 FELUPE 계산 3개가 성공했다. 모든 IP의 원 stress/F tolerance·평형 관문과 point pair가 PASS다. 기존 Simulation 저장/owner 종료/새 owner 읽기에서 job3개가 유지됐다. native assignment는 이 실행에서 `NOT_TESTED_PUBLIC_SYNTHETIC_MESH`다. |
| 별도 새 Python process의 FE 보존 읽기 | `law-native-windows-cold-02/read/receipt.json`: 같은 세 Simulation/result hash를 새 process에서 읽었고 job3→3, 새 job0, evaluation call0이다. |
| 실제 Windows Qt normal/narrow | `law-native-windows-qt-native-02/`와 교정 뒤 `law-native-windows-qt-product-03/`: Windows QPA로 실제 Qt 창을 열고 닫아 3법칙의 두 크기와 전달값 표를 확인했다. offscreen 첫 캡처의 한국어 글리프 누락을 실제 Windows 표시의 결함과 혼동하지 않는다. 원/교정 전달창의 같은 조건 비교 그림은 `law-native-transfer-visual-comparison-01/`에 있다. |
| 전달 오류/응답 유실·FE 문맥 | `law-native-windows-recovery-04/`: 실제 loopback HTTP/Qt의 source 변경 사전거절, 등록 전·후 응답 유실, 같은 요청/ID 복구, 나중 메모 보존, 잘못된 solver ID 두 반례 등 10 pass. native transaction은 controlled fixture이며 FreeCAD 실행 증거가 아니다. 이 묶음에서 발견한 fit 창 연결 실패도 보존했다. |
| 기존 피팅 창 연결과 입력 보호 | `law-native-windows-fit-ui-05/`: 실제 HTTP로 기존 NumericalWindow의 `mode=fit`/법칙6계수/시험·holdout 편집을 열고 새 계산0을 확인했다. caption 변경 신호가 입력 변경으로 취급되던 생성자 결함을 함께 교정했으며 3법칙 표시와 합쳐 4 pass다. |
| 유실 뒤 문맥 변경의 거절 복구 | `law-native-windows-recovery-06/`: 등록 전 유실 뒤 native generation이 바뀌어 같은 요청이 거절되는 반례를 추가했다. 같은 ID의 미등록과 같은 서비스 session을 함께 확인한 뒤 편집으로 복귀하며, 404만으로 미적용을 추정하지 않는다. 기존 사전거절·등록 전/후 유실과 합쳐 실제 HTTP/Qt 4 pass다. |

Sol의 국소 교정은 전용 Qt2파일과 관련 테스트뿐이다. 적용 전 HTTP 거절은 등록 실패로 확정되는 경우에만 검토를 무효화하고 편집으로 돌아간다. 응답 유실·없는 상태 조회만으로 미적용을 추정하지 않으며 원 document/op/arguments/session/generation/command ID를 보존해 같은 요청으로 복구한다. 그 정확한 재시도가 거절된 경우에도 같은 서비스의 원 receipt 또는 명시 미등록 상태를 조회해 잠김을 회복한다. 계수·원단위·적용값 표를 주화면에 두고 전체 JSON은 기술 상세에 보존한다. 기존 피팅 창의 계수·시험·holdout 흐름을 재사용한다.

실제 FreeCAD 1.1.4에서 DP의 명시 할당·Undo/Redo·FCStd 저장과 새 프로세스 읽기도 확인했다.
그 저장 파일을 수정하지 않고 또 다른 FreeCAD owner로 열어 입력을 고정한 뒤,
반환된 정확한 입력으로 FELUPE 계산 한 번과 Simulation 저장·별도 Python 프로세스의
보존 결과 읽기를 완료했다. 재적용·재서명·새 시편 생성은 없었다.

`_workspace/delivery-data-material/law-native-c1-windows/summary.json`과 `native/run/cold`의
원 기록을 따른다. 계산은 8 Hex8, 시점마다 64적분점이며 point–FE 대응·자유 DOF 평형·
수락 상태 격리를 원 허용치로 통과했다. cold 읽기는 새 작업·계산·FELUPE import·옛 출처
파일 접근이 없었다. 원 FCStd·동결 입력·앞선 실패 Job과 수치 소스는 불변이며 세 소유 Job은
정상 종료했다. 출처 경로를 실행 경로로 오인하던 원 실패와 Pro C1 교정 전후를 구분한다.

이는 해당 공개 DP 시편의 실제 연결 확인이다. 전체 GUI의 OS 조작, 일반 형상·다른 요소·
전체 재료군이나 강도·물리 qualification 승인으로 확대하지 않는다. 전체 인도4 완료도 아니다.

## Pro 작성 환경의 원기록

## 최종 좁은 검사

`evidence/final-small-check/receipt.json`과 stdout/stderr가 실제 기록이다.

```
python -m pytest -q tests/law_native tests/test_ns1_material_limits.py \
  tests/test_hyperelastic_reference.py::test_full_hessian_and_pk1_are_independent_scalar_energy_derivatives
54 passed, 8 skipped
```

54 pass는 새 법칙/단위/상태/접선/전송의 Python 검사, 기존 J2 제한 회귀, 원 SVK independent scalar-energy oracle를 포함한다. 8 skip은 FELUPE 실제 runtime 필요 검사 7개와 PySide6 모듈 1개다. skip을 pass/actual FE로 세지 않는다. 자체 supervisor는 return0 / CONFIRMED_REAPED를 기록했다. 패키징 시 clean patch 후 반복 검사 기록은 별도 `patch-apply-small-check`에 남으며 원 수행 횟수에 합산해 품질을 과장하지 않는다.

| 요구 영역 | 작성물/관측 | 실제 분류 |
|---|---|---|
| DP 직접/독립 p–q/J2 한계/제하·apex | 전용 구성 적분·명시 내부 상태·discrete tangent; 독립 scalar/FD 검사 | Linux 실제 PASS |
| yield/apex/실패 tangent/초기 state 복원 | injected wrong tangent FAIL, accepted prefix 유지, local/partial response 보존 | 실제 Python 검사 PASS; 물리 FE 아님 |
| SLS 원 canonical9/refined17 및 τ 변경 | 원 FIXED_LIMITS 그대로 stress/state/energy; 비영 초기 viscous state | Linux 실제 PASS; MFront compiler/worker 실행 아님 |
| Neo point/회전/physical9 및 3법칙 spatial FE | 실제 FELUPE adapter/worker/reader·각 IP 비교·입력/expected/tests | 소스 작성, 실행 NOT_RUN |
| 原 SVK/J2 | 원 소스 변경 없음, J2 원 공개 table/policy·NS1 limit, SVK scalar-energy derivative | 관련 작은 회귀 PASS; 새 native 실행 아님 |
| fit/Data/holdout/CAS/evidence/cold | 실제 기존 Data4 imports + Numerical fit1, 명시 k0 채택/동일 명령 replay/새 owner | 실제 Linux 기존 owner/엔진 PASS |
| Material revision/preview/source conflict | 실제 기존 MaterialDocuments/Workbench 저장·순수 snapshot/invalid raw/cold | 실제 Linux PASS |
| Native typed preview/apply/rollback/guard/유실응답 | 기존 native queue와 controlled FEM owner fixture | fixture PASS; 실제 FreeCAD 아님 |
| 실제 FCStd Apply/Undo/Redo·새 process | 소유 process 2개 smoke/macros·실제 source→native 입력 작성 | NOT_RUN |
| Qt normal/narrow/dirty C01 | 기존 Material/inspector/transfer 연결 및 작은 실제 GUI test | PySide6 미설치, NOT_RUN |
| Windows/ABI/실제 binary hashes | 고정 설치 경로·runtime recorder·분리 worker 제공 | 실제 Windows NOT_RUN |
| 성공/실패/timeout finally | 실제 직접 연 3개 프로세스 | 각각 종료 확인, 의도한 FAIL/TIMEOUT 보존 |

## 실제 fit 수치

두 번째 독립 실행 `evidence/fit-workflow-02/workflow-receipt.json`:

- 합성 인장/전단 fit, 압축/구속편차 holdout. 실제 Data 원샘플/행·단위·측도/frame·weight·fit inclusion을 기존 엔진이 소비했다.
- 식별 k0=249.9999999999997 MPa. E,nu,alpha,beta,H는 고정했다. 총 job5개(Data4+fit1), cold read의 자동 추가 job0개.
- 인장 RMSE9.912455715365497e−12 MPa, 전단1.1457157353758233e−13, 압축 holdout1.946835230858563e−12, 구속편차 holdout9.63659423531719e−12.
- 후보 C000010의 실제 candidate evidence를 저장하고 CAS 채택, Material/Plan save, 기존 owner shutdown, 새 Workbench에서 동일 결과 hash를 확인했다. 이는 실측 재료 식별성/파괴 강도 인증이 아니다.

원 workspace와 source-snapshot/compiled input/보존 original result가 ZIP evidence에 있다. 추가 `cold-process-result/receipt.json`은 원 workspace의 별도 copy를 다른 실제 Python 프로세스에서 열어 Material 입력·원 결과 hash와 retained 10개 source를 확인한 PASS이며 새 job은 0개다. 직접 연 프로세스의 finally 종료도 확인했다. 첫 fit 실행도 다른 source snapshot의 기록으로 보존했다. source 변경 이전의 성공을 최종 source 증거로 혼용하지 않는다.

## 실패를 지우지 않음

`development-check-01.log`: 최초 SLS FD mismatch. F≈I에서 아주 작은 perturb를 F에 더한 round-off 문제가 있어 허용치를 완화하지 않고 Kelvin 좌표 직접 perturb로 수정했다. `development-check-02.log`는 수정 후 결과다.

`pytest-01.log`: 최초 elastic state까지 yield residual equality를 요구한 잘못된 검사 1건 FAIL을 보존한다. plastic은 equality, elastic은 inequality를 요구하도록 교정했다. production DP/reference 값은 이 테스트 오류를 맞추기 위해 변경하지 않았다.

`install-felupe.log`: 실제 pip DNS 연결 실패. wheel download tool 실패는 별도 environment/NOT_RUN 기록에 구분한다. `runtime-rejection/`는 실제 no-runtime fixed FE worker를 실행해 REJECTED 및 FE_execution NOT_RUN과 입력·stdout/stderr를 보존한 검사다. 이를 FE 성공으로 해석하지 않는다.

`process-finally/`의 deliberate RuntimeError exit1 및 TIMEOUT 종료(-9)는 실패 사례 자체를 지우지 않고 cleanup만 성공으로 판정한 기록이다.

## 닫히지 않은 실제 인수

root는 통합한 실제 Windows pin 환경에서 DP/Neo/SLS 각각 spatial solver 실행·동일 point→FE pair PASS, native saved Material→현재 FreeCAD Apply/Undo/Redo/FCStd 새 프로세스, 그 frozen 입력의 실제 Simulation/reader cold를 확인해야 한다. 이 실행에서 발생한 원 residual/실패를 tolerance 상향으로 지우지 않는다. PySide6 normal/narrow와 C01 세부 사용성은 Sol/root, 독립 constitutive/source 검토는 Astra 담당이며 이 인도에서 수행했다고 주장하지 않는다.

코드 admission은 별도 whole-solid Hex8 준정적 시편이다. 일반 임의 형상의 nonhomogeneous FE field와 point 비교는 공개 homogeneous pair의 물리 가정에 맞지 않으면 pair FAIL이 될 수 있다. plane/shell/beam/contact/J2/dynamic/Impact/고온/다중 branch/일반 사용자 소스·새 SVK Windows pair는 새 지원으로 등록하지 않는다. 배포와 실행 인수 후에도 실측 calibration/strength/failure/공학승인은 UNKNOWN이다.

기존 material.felupe/J2/MFront SVK/Maxwell 지원·원 실패/수치 기준은 유지한다. 이번 추가 pair로 전체 재료군·전체 제품이 완료됐다고 선언하지 않는다.
