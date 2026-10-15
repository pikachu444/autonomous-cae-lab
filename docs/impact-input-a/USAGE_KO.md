# 충격 입력을 열고 계산하기

현재는 아래 Python 예제와 기존 Simulation API에서 입력을 편집하고 계산할 수 있다.
화면에서 추가 원문 편집 기능을 사용하는 연결은 아직 남아 있다. 입력 편집·저장·결과
읽기에는 CAD·AI·MCP·WSL이나 유료 API가 필요하지 않다.

## 실행 준비

현재 저장소를 하위 모듈과 함께 내려받고 [Windows 설치 안내](../INSTALL_KO.md)를
따른다. 기존 설치는 저장소를 갱신한다. 아래 명령의 `python`은 설치 안내에서 확인한
제품용 Python 실행 파일을 사용하며 저장소 루트에서 실행한다.

실제 계산에는 기존에 등록한 무료 Windows OpenCourant가 필요하다. 예제 실행기가
솔버를 새로 설치하거나 구매하지는 않는다. 런타임이 없어도 계산을 요청하지 않는 입력
편집·저장 예제는 사용할 수 있다.

## CAD 없이 지금 실행할 수 있는 공개 입력 검사

각 명령은 **없는 새 작업 폴더**를 지정한다. 이전 결과를 덮어쓰지 않는다. 기본 동작은 가져오기→명시 편집→기존 Simulation 저장→별도 Python 프로세스에서 같은 입력 재열기이며 native/runtime 조회를 하지 않는다.

```powershell
python examples/impact/input_a/run_public.py --workspace C:/CAE/A-native-edit --route native
python examples/impact/input_a/run_public.py --workspace C:/CAE/A-assembly-edit --route assembly
```

native 예제는 원 Starter/Engine/includes를 보존하고 종료 시간만 0.001→0.0012 s로 원문 hunk 편집한다. assembly 예제는 회전·이동한 두 instance 중 BODY-2 집합에 Vz=-100 mm/s를 명시하고 원 local 절점20의 Z 변위/속도를 선택한다. 내부 effective 번호나 hash를 사용자가 입력할 필요는 없다. 예제 코드는 선택 대응을 명시 수락한 뒤 같은 문서에 적용한다.

실제 Windows에 기존 pinned runtime이 등록돼 있을 때만 다음 **하나의 작은 경로**를 실행한다. 신규 binary 설치/다운로드나 다른 runtime 대체는 하지 않는다.

```powershell
python examples/impact/input_a/run_public.py --workspace C:/CAE/A-native-run --route native --run-native
```

이 명령은 기존 simulation.evaluate로 단일 Job을 제출한다. Starter→Engine→TH/ANIM reader→Post 등록→원 시각/ID의 응답 선택→저장→별도 프로세스 재열기를 실행한다. 별도 프로세스에서는 solver를 실행하지 않는다. Linux에서 `--run-native`를 지정하면 NOT_RUN과 exit 2를 반환하고 입력만 저장한다. native 계산을 성공시킨 것으로 해석하지 않는다. 계층 변환 경로를 따로 확인할 때만 별도 새 폴더와 `--route assembly --run-native`를 사용한다. 큰 campaign은 필요 없다.

Ctrl+C는 현재 Job에 취소를 요청한다. 실제 종료 여부는 기존 owned 프로세스 finally 및 cleanup 기록이 결정한다. 종료 미확인은 FAILED로 남기며 다음 검사를 성공처럼 이어 가지 않는다. 런타임 부재/Starter 오류/Engine 실패/후처리 실패의 원 자료는 해당 workspace에 남는다. 같은 작업의 timeout을 임의로 늘리거나 강제 종료를 정상 종료로 바꾸지 않는다.

## Windows 입력 개정과 시간적분 설정

Pro 원 작성 환경은 Linux였고 Windows solver는 미실행이었다. Sol의 실제 Windows 검사에서
원 공개 native 레시피의 자동 Ismstr/Itetra4=3 조합과 CFL 0.9 문제가 드러났다. 원 실패
계산·입력은 별도 작업 폴더에 보존하며 사용자 파일을 자동으로 바꾸지 않는다.
현재 공개 native 입력은 탄성 C3D4의 표준 Itetra4=1000을 명시하고 `/DT` scale=0.5,
minimum step=0을 사용한다. mass scaling, 재료·단위·연결·출력 시간과 아래 물리 공차는 바꾸지 않았다.

이 작은 tetra의 독립 선형 tangent/lumped-mass 고유치 상한은 약 7.8467e-7 s다.
CFL 0.9의 실제 초기 간격 8.2108e-7 s는 이를 초과했다. 이 계산은 실제 total-strain solver의
전체 구현 재현이나 일반 모델의 안정성 보증이 아니다. [공식 시간 간격 설명](https://help.altair.com/hwsolvers/rad/topics/solvers/rad/element_time_step_r.htm)과
[`/DT` 카드](https://help.altair.com/hwsolvers/rad/topics/solvers/rad/dt_engine_r.htm)의 scale 적용을 사용한다.
기존 INP 변환 경로의 레시피는 별도 검토 대상이며 native 사례의 결과로 계층 INP까지 수용하지 않는다.

## 사전 선언 예상량

길이축 10 mm의 균질 C3D4: 체적 1000/6 mm³, ρ=7.8e-9 Mg/mm³, 질량 1.3e-6 Mg = .0013 kg. Vz=-100 mm/s, g=0이므로 전체 KE=.0065 N·mm=6.5e-6 J, 실제 기록된 t에서 Uz=-100t mm다. native는 한 tetra이며, assembly는 동일 두 tetra 중 하나만 이동하므로 전역 질량은 .0026 kg이고 KE는 동일하다.

공개 검사 허용량은 변위 absolute 5e-5 mm, 속도 absolute .05 mm/s, 질량 relative 5e-6+absolute 1e-12 kg, KE relative 5e-4+absolute 1e-12 J다. 이는 파일/단위/시간/선택과 균일 병진의 작은 smoke 검사에 대한 사전 선언이며 공학 강도·수명·실험적 승인 기준이 아니다. 텍스트 converter 반올림과 명시적 선형 균일 병진을 고려한 수치 여유다. 원 Pro 작성 환경에서는 Windows 미실행이었다. 아래 Windows 국소 확인은 개정한 공개 native 입력 한 사례에만 해당한다. 기존 Starter/Engine/time coverage 관문은 이 허용량과 별개이며 낮추지 않았다.

입력으로 적분한 연속체 COM은 (2.5,2.5,2.5) mm, COM 관성은 대각 9.75e-6 / 비대각 1.625e-6 Mg·mm²다. **이 행렬은 solver 강체의 lumped inertia가 아니다.** `/RBODY` native readback 미구현을 이 값으로 대체하지 않는다. 코드의 initial_mass_properties.json은 native_body_mass_inertia=UNKNOWN을 유지한다.

## 기존 앱에 연결할 작업 순서

‘입력 열기’에서 제출 root, INP 또는 Starter/Engine, 원 단위를 선택한다. 파일 목록/instance·local ID/집합·면 표와 원 위치를 확인한다. ‘원문 보기’의 선택 범위를 ‘수정할 원문’에서 바꾸고 ‘선택 범위 적용’을 누른다. `editor_buffer/apply_display_range`가 Qt의 LF 화면 위치를 원 ASCII/CRLF byte 범위로 변환하므로 손대지 않은 줄바꿈을 바꾸지 않는다. native 수치 표는 `apply_native_field`를 사용한다. 내부 JSON/hash/raw byte offset은 화면 입력 항목이 아니다.

원문 편집으로 effective 번호나 집합 구성원이 달라지면 ‘기존 대상 / 현재 대상’ 대응 표를 확인하고 원 instance/local ID로 다시 선택한다. `impact_reference_bindings.review/accept_review`는 그 명시 수락을 저장한다. 단순히 예전 정수 ID가 여전히 존재한다는 이유로 새 대상에 붙이지 않는다. ‘적용’은 기존 `simulation.update`, ‘저장’은 `document.save`, ‘계산’만 `simulation.evaluate`다. 초안 진단이 있어도 저장은 가능하고 실행만 차단한다.

결과는 **원 Job의 고정 입력**에 붙인다. 현재 편집 중인 다른 revision을 사용해 옛 결과를 대응시키지 않는다. `document_result(document_id, job_id, selection={"responses":["impact.velocity.Z@2"]})` 등의 domain 호출에서 내부 숫자는 source 선택으로 해석한 값이다. 단일 frame API는 `impact_retained.select_frame`; metadata 목록은 `inventory`이며 payload 검증 상태가 다르다. 없는 프레임/성분/active 값은 UNKNOWN 또는 명시 오류다.

## 실패 자료 다시 읽기

같은 Simulation에서 원 계산을 선택하고 ‘보존 결과 다시 읽기’를 명시한다. 아래는 내부 연결 예다. GUI에서는 원 계산 선택과 ‘원 ANIM/TH 다시 변환’ 선택지만 보이면 된다.

```python
reply = workbench.document_command(
    document["id"], "simulation.reprocess",
    {"source_job_id": original_job_id, "convert_raw": False},
    session_id=document["session_id"],
    expected_generation=document["generation"], command_id=unique_command_id,
)
```

False는 이미 보존된 VTK/CSV만 읽으며 runtime 조회도 하지 않는다. True는 원 native ANIM/TH를 동일 pinned converter로 다시 변환한다. True 경로는 이 작성환경에서 실제 converter 실행 NOT_RUN이다. 새 Job 결과의 READBACK_ONLY/solver_execution=NOT_PERFORMED와 source_execution_status를 함께 보여야 한다. 새 읽기가 성공해도 원 FAILED/CANCELLED를 SUCCEEDED로 바꾸지 않는다. 원 Job·현재 선택·입력과 결과를 저장한 뒤 새 owner에서 다시 읽는다.

## 검증과 잔여

원 인도의 RESULTS.md/RESULTS.json은 Pro 작성 당시 Linux 실행·synthetic 경계 대역·Windows 미실행을 구별한 기록이다. 후속 Sol Windows 통합 결과는 아래와 구별한다. A 전체 인수는 미완료다. `/RBODY`, native TRANSFORM/INIVEL AXIS 등 rigid readback 잔여와 Sol GUI 연결 및 실제 Windows/Post 확인이 남는다. B/C는 별도 배정 범위를 유지한다.


## Windows 국소 확인 — 2026-10-15

기존 Windows runtime latest-20261011/cb760c2의 binary/CFG hash를 확인하고 새 설치 없이
기존 Simulation/JobManager/owned process로 공개 native 입력을 실행했다. 작성·통합 교정은
Sol이며 원 Pro 구현과 원 실패 입력·로그는 그대로 보존했다.

| 범위 | 실제 결과 |
|---|---|
| 원 레시피와 CFL 0.9 | 첫 실행은 Engine 정상 종료에도 요소 삭제·에너지 폭주로 물리 검사 FAILED. 명시 Ismstr=2 시도는 Starter 경고2037로 Engine 전 차단. Itetra4=1000만 명시한 CFL 0.9도 물리 검사 FAILED |
| 개정 native 입력 | Itetra4=1000, `/DT` scale=0.5를 명시. Starter warning0/error0, Engine 정상 종료2632cycles, 실제 ANIM13프레임과 TH120표본 변환 |
| 사전 물리 공차 | 변위 최대 오차1.39e-17mm, Vz·전체 질량·KE 최대 오차0. 원 단위/접속/밀도/재료/질량 스케일링과 수용 공차 불변 |
| 실제 시각 | ANIM 0→0.00120015s, TH 0→0.001190115s. 요청 종료0.0012s 값으로 보간하지 않고 기록된 각 시각에서 비교 |
| 저장·새 프로세스 | 원 입력과 정확한 선택 결과 hash가 새 Python owner에서 같음. 새 Job0, solver0 |
| 프로세스 종료 | 360s 고정 상한 안에40.90s, exit0. outer Windows Job은 job_empty, owner shutdown joined |
| 기존 ParaView | 정확한 PVD/등록 참조를 기존 Post 담당에게 전달. 이 기록 시점의 실제 창 열기·저장·새 프로세스 재열기는 별도 미완료 |
| 계층 INP/강체/전체 A | 이번 native 사례로 수용하지 않음. 계층 변환의 기존 recipe 검토, `/RBODY`·TRANSFORM·AXIS와 전체 GUI 작업 잔여 유지 |

로컬 근거는 `_workspace/a-native-01`~`a-native-04`,
`_workspace/delivery-structure-impact/impact-input-windows-native-01`~`04`이다.
최종 정상 계산은 `a-native-04/input-a-check.json`, 선택은 `input-a-selected-result.json`,
별도 프로세스 읽기는 `input-a-cold-read.json`에 있다. 앞선 실패 결과는 덮어쓰지 않았다.
이 작은 탄성 병진 확인은 일반 충격·강도·수명 또는 실험적 적합성의 승인이 아니다.


재후처리는 현재 편집 초안의 계산이 아니다. 원 입력 D0를 계산한 뒤 문서를 D1로 편집했어도,
새 읽기 Job의 snapshot/hash/revision/generation은 원 D0로 함께 기록한다. 현재 D1 초안은
유지하고 제출 응답 유실 뒤 복구에서도 같은 D0 식별 정보를 쓴다. 이 후속 연결은 원 계산이
정상·실패·취소인 세 대역 경계 사례에서 저장/새 owner/result reference까지 확인했으며,
새 native 계산은 하지 않았다. TH/TITLES 부재나 잘린 CSV에서 독립 VTK/완결 prefix를
복구하는 넓은 부분 결과 처리는 아직 미완료다.
