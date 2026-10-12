### C01. 복수 owner, 셀 입력, 저장·닫기와 다른 client

Material+Plan 창은 같은 `MaterialDocument`와 `NumericalDocument`에 연결한다. 문서 두 개의 독립 수명을 한 창에 보여준다. 예시는 `Rubber · r17 · draft g42`와 `Fit A · r8 · draft g21`이다. 계수 `현재값`은 파랑 Material, `Plan 시작값/하한/상한/자유`는 보라 Plan 머리글이다. 색과 함께 owner 이름/아이콘/도움말을 쓴다.

| 사용자 행동 | 정확한 변경·결과 | 실패·되돌리기와 다음 행동 |
|---|---|---|
| Material μ 셀에 `0.9e`를 입력 | 셀 buffer에 문자열 보존. 계산에 사용하지 않음. Enter는 parse 진단, Esc는 편집 시작값으로 복귀 | `입력 마침/원문 초안으로 보존/입력 취소`를 셀에서 선택. 현재 owner가 invalid raw draft를 지원하는 필드는 원문으로 commit 가능; 숫자0 대체 금지 |
| 유효한 μ=.90 MPa Enter | `material.update` 한 변경, Material g43 dirty. Plan r8 source는 r17 그대로 | Undo 메뉴 `Material: μ 변경 취소`. Plan Undo와 혼합하지 않음 |
| Plan 상한1.4→1.2 입력 | `numerical.update` 한 변경, Plan g22 dirty. Material 허용 범위/현재값은 불변 | Undo 메뉴 `Fit A: μ 상한 변경 취소` |
| 여러 owner 열에 붙여넣기 | 적용 미리보기에서 Material/Plan 값과 영향 분리; owner별 validation/CAS 후 receipt 표시 | 한 owner만 성공하면 성공/실패 행 분리, 전체 성공 toast 금지. 실패 buffer는 남고 성공은 자기 Undo 가능 |
| Ctrl+S | 포커스 owner 저장. 제목과 버튼은 `Save Material` 또는 `Save Plan`. `Save workspace drafts…`는 별도 명령 | native 미확정 Task/유효하지 않은 buffer는 먼저 위 선택. 뜻을 보존할 수 없는 buffer는 recovery capsule로만 보존하고 saved revision이라고 부르지 않음 |
| 두 문서 저장 | Material r18 게시 성공, Plan 저장파일 쓰기 실패이면 `SAVE-PARTIAL`: Material r18 ✓ / Plan r8 + dirty g22 ! | 두 문서가 함께 저장되었다고 표시하지 않음. `Retry Plan / Save Plan branch elsewhere / Keep working`. 이전 Plan r8과 현재 dirty 유지 |
| 저장한 Material을 Plan에 반영 | `Refresh source…`에서 r17→r18, μ .85→.90, protocol/observations/변수 시작값 차이 표시. `Use new source + copy selected starts` 또는 `Keep current Plan` | 갱신은 Plan의 명시 한 변경. source 재검증·진단 후 Plan 저장. Material 저장 성공만으로 source/ref/Plan starts 자동 변경 금지 |
| 다른 client가 같은 μ 수정 | owner의 expected generation/session 확인. 미확정 겹침은 BUSY_EDIT, 기존 세대는 STALE_DOCUMENT | `CLIENT-CONFLICT`에서 Base r17 / Local buffer / Current r18 비교. `Read current`, `Propose on r18`, `New branch`, `Cancel`. 유효한 최신 대상과 새 command ID로만 명시 재제안 |
| 창 닫기 | `CLOSE-DIRTY` 표에 각 owner buffer/draft/saved, 미저장 항목, 진행 job이 각각 표시 | `Save selected and close`, `Keep recovery drafts and close`, `Discard selected changes and close`, `Return`. 실패 owner 있으면 닫기 중단. job cancel은 별도 checkbox 기본 OFF |
| 닫기 후 다시 열기 | 새 owner process에서 정상 saved revisions와 별도 recovery 후보를 제시. recovery를 선택하면 새 dirty session | 자동 solver/fit/provider 재실행 없음. 버전 미지원은 보존 결과 읽기/원문 export; 원본 migration은 사본 검증 후 명시 전환 |

`Keep recovery drafts`의 capsule은 문서 ID/base revision/session/generation, raw buffer의 cell locator/원문/단위, acknowledged draft, 참조 해시, 미결 save receipt, 보존 결과 refs를 가진다. capsule 쓰기 실패면 닫기를 완료하지 않는다. 이것은 제품 설계이며 planning prototype의 로컬 JSON 복구와 production crash durability를 동일시하지 않는다. 공통 서비스의 기존 immutable revision 쓰기/verification/committed pointer를 재사용하고 per-owner 성공을 정확히 표시한다. 실제 복수 owner adoption은 모두 검증·준비 후 adoption-set 참조를 마지막에 게시하는 확장이다. 네트워크/디스크 실패 때문에 자동 rollback 성공을 주장하지 않는다.

### C02. 두 CSV에서 Material fit까지의 물리·관측 계약

시안의 모든 값·곡선은 `data/README.md`에 정의한 합성 자료다. A/B는 같은 시편을 임의 분할한 데이터가 아니라 서로 다른 합성 specimen이다. B 전체를 holdout으로 정한 뒤 fit 예산을 고정한다. 실제 장비 데이터를 가진 것으로 표시하지 않는다.

| 원본 | 실제 열 순서 | 사용자가 DATA-MAP에서 지정 | 수치 변환·출력 |
|---|---|---|---|
| tensile_A.csv | time_s, force_N, extension_mm, temperature_C | time/time axis, force, extensometer extension, absolute temperature | t[s]=raw; F[N]=raw; ΔL[mm]=raw; T[K]=T[°C]+273.15 |
| tensile_B.csv | extension_um, temperature_K, load_kN, time_ms | extension, absolute temperature, force, time | ΔL[mm]=raw×.001; T[K]=raw; F[N]=raw×1000; t[s]=raw×.001 |

열 이름 변경/metadata의 단위 지정은 수치 변환과 다른 명령이다. 자동 추정은 미리보기이며 사용자가 확인한다. 같은 이름 Stress/strain으로 measure를 추정하지 않는다. 필수 역할 중복·누락, unit dimension 불일치, time 비단조는 해당 열/행에 표시한다. ΔT에는273.15 offset을 적용하지 않는다. 원본/행 식별/채널 ID는 유지하고 recipe output으로 canonical channel을 만든다.

시험 geometry는 `L0=50 mm`, `A0=20 mm²`; displacement 의미는 **extensometer gauge extension**이다. crosshead 변위만 주어졌을 때 이를 gauge strain이라고 바꾸지 않으며 machine compliance/게이지 위치가 없으면 해당 관측을 미확인 또는 직접 force–displacement로 남긴다. 관측은 `e=ΔL/L0`, `λ1=1+e`, `P11=F/A0`로 계산한다. 여기서 P11 단위 `N/mm²=MPa`, measure=`first_Piola`, frame=`material_cartesian`, 축은 시간[s]에 대응한 이력이다. 곡선 표시 x축 e와 evaluator 이력의 독립축 time을 구별한다. loading/unloading에서 같은 e가 반복되면 e로 정렬해 시간 이력을 잃지 않는다.

Cauchy 변환은 `σ11=(λ1/J)P11`이다. `J`는 실제 transverse 측정/완전한 F 또는 명시 가정에서 얻어야 한다. 면적 일정 또는 비압축성 J=1을 기본값으로 넣지 않는다. `ln λ1`은 λ1>0에서만 유효하다. 축별 strain/stress measure, 좌표 방향, 관측 위치를 함께 저장한다.

`MAT-PROTOCOL`은 다음 둘을 눈에 보이게 구별한다.

| 시험/평가 종류 | 입력·기본값·종속 조건 | 현재 코드 / 새 구현 |
|---|---|---|
| Prescribed deformation gradient | 모든 Fij 무차원; off-diagonal 기본0, F22/F33 기본1, F11=1+e; t 단조; detF>0 | 기존 FELUPE adapter. 이 default는 횡변형 구속이며 traction-free가 아님 |
| Uniaxial traction-free | F11 prescribed; lateral target P22=P33=0 MPa, initial λ2=λ3=1, 허용오차·최대반복은 지원 evaluator가 소유 | mixed-control material-point solve/실패 진단 추가. 현재 adapter의 capability 없는 경우 draft 저장 가능, 실제 Evaluate/Fit 차단 |
| Measured transverse history | t와 F22/F33 또는 횡 strain measure/방향 채널, 유효 구간/uncertainty | mapping + full F validation; 관측값 누락을1로 채우지 않음 |

합성 시안의 후보 비교는 traction-free protocol을 의도한 **SIMULATED** 결과다. 이는 현재 FELUPE adapter가 그 시험을 실행했다는 증거가 아니다. 현재 지원 prescribed-F 시험을 별도로 선택하면 그 이름과 기준으로 직접 평가를 할 수 있다. `.ui` 또는 화면의 버튼 enabled는 planning state이며 실제 capability gate 통과가 아니다.

### C03. 구간·mask·학습·holdout·잔차와 상세 결과 보존

DATA-EDIT에서 row40..110을 선택하면 곡선 구간과 정확 sample ID가 동시에 강조된다. 표의 정렬·열 이동 뒤에도 선택 의미는 sample ID로 보존한다. 곡선 brush는 time 범위인지 row 집합인지 작은 mode control에 표시한다. Ctrl 클릭 추가, Shift 연속범위, `Exclude quality`/`Restore quality` 컨텍스트 메뉴와 메뉴 대안을 둔다. 렌더링 decimation과 실제 계산 sample count를 다르게 표시한다.

| mask/선택 | owner | fit에 대한 의미 |
|---|---|---|
| 원자료 품질 mask, 센서 포화 등 | Data | 근거와 원값 남김; 사용불가 원행 제외 |
| 변환 유효성, det/로그/보간 support | recipe owner | 연산 불가를0으로 채우지 않고 제외 사유 보존 |
| 학습 구간/관측 선택 | Plan | 이번 연구 objective의 고정 sample selection |
| train/holdout | Plan experiment | holdout은 목적함수에 들어가지 않음 |
| 숨김, legend mute | View | 통계/fit 제외가 아님 |

실행 전 compiler가 `quality ∩ operation-valid ∩ Plan inclusion`을 채널의 안정 sample ID→원행→imported index로 매핑하고 고정한다. 현재 Data quality_rows와 Numerical Plan의 schema/compiler는 이 계약을 완전히 제공하지 않는다. 이를 **실제 추가 schema/compiler 작업**으로 backlog에 배정한다. 화면에서 줄을 회색으로 칠하는 것만으로 제외를 구현했다고 하지 않는다.

기존 curve alignment와 residual은 유지한다. 관측 e의 사용 sample 수를 n_e, curve weight를 w_e>0, scale을 s_e>0라 하면:

`r_ei = (prediction_ei − observation_ei) × sqrt(w_e / n_e) / s_e`

`objective = Σ_e Σ_used_i r_ei²` (train experiments만).

scale은 선택 응답 단위(예시0.05MPa), residual은 무차원이다. raw residual ΔP[MPa], RMSE[MPa]와 scaled residual/objective를 별도 탭에 표시한다. curve별 n으로 정규화하므로 sample 수가 많다는 이유로 곡선이 자동 우세하지 않는다. 화면에 이미 n 정규화가 적용됨을 짧은 formula tooltip으로 밝힌다. 기본 w=1, scale=1 response unit은 기존값이며 실제 시험 noise/uncertainty와 같다고 부르지 않는다. uncertainty를 기반으로 s를 채우는 동작은 값/출처를 명시 승인한 편집이다.

현재 정렬은 단조 named axis/unit 일치와 명시된 구간의 linear interpolation이다. 외삽 금지. 계산 gap이 있으면 exact sample만 허용한다. Post의 별도 시간·공간 비교 recipe를 fit 정렬로 재사용한 것으로 표시하지 않는다. 비단조 이력은 time 축으로 유지한다. 무효 sample count, 제외 사유, actual n, 양 끝 support와 gap을 실행 전에 표에서 확인한다.

`MAT-FIT-PARTIAL`의 후보표에는 물리 응답/objective/검색 penalty/실행 상태/곡선 보존/holdout을 별도 열로 둔다. 코드의 현 한계는 arbitrary candidate의 모든 상세 곡선과 holdout을 보장하지 않는다는 것이다. 최종 선택 후보에 대해서만 보존된 상세와 holdout이 있을 수 있다. 따라서 예시는 다음과 같다.

| 후보 | train objective | 실행/곡선 | holdout | 가능한 다음 행동 |
|---|---|---|---|---|
| c017 μ=.862 | 0.00184 | valid / retained selected result | evaluated, RMSE .014MPa (합성 예시) | 원값/잔차 확인 → 채택 제안 |
| c014 μ=.901 | 0.07908 | valid summary / NOT_RETAINED | NOT_EVALUATED | `Evaluate details + holdout…`로 새 evaluation과 별도 예산/기록 확인 |
| c009 | — | evaluator failure / 실제 진단 보존 | NOT_EVALUATED | 실패 입력/로그 → 수정 또는 새 평가 |
| c021 | — | CANCELLED / partial retained | NOT_EVALUATED | 보존 부분만 열기, 탐색 자동 재개 없음 |

후보 클릭/정렬/재열기는 계산을 발생시키지 않는다. 추가 평가는 `detail_eval` 새 ID로 원 후보에 연결하고 원 실행의 기록을 소급 채우지 않는다. 실제 실행이 없으면 위 숫자는 UI fixture임을 유지한다. 실행 전 retention policy에서 최소 모든 후보 입력/상태/응답/진단/기존 refs를 보존하고 선택/비교/채택 근거의 상세가 없으면 보존까지 완료한 뒤에만 해당 행동을 완료 처리한다. 메모리 cache8 항목을 영구 보존 계약으로 오인하지 않는다.

### C04. 후보 채택과 실행 입력의 고정

시안의 Material r17 μ=.85에 대한 c017 μ=.862가 도착했지만 다른 client가 r18 μ=.90을 저장했다. `MAT-ADOPT-CONFLICT`는 base .85 / candidate .862 / current .90, source result/Plan revision, 바뀐 대상과 지원 law를 같은 표에 보여준다. `Use candidate on current r18`은 r18을 읽어 새 변경 제안으로 prepare하고 기대 generation을 다시 검사한다. `New Material branch`는 새 문서 ID, `Cancel`은 현재 r18과 후보를 모두 유지한다. 버튼을 누르기 전 current 값을 바꾸지 않는다.

Model current 값, Plan 시작값, source ref는 별개다. Material r19를 저장한 후 `Refresh Plan source`에서 명시 갱신·변수 연결을 검증한다. 후보가 바꿀 수 없는 derived/read-only 변수와 native domain 허용범위는 유지한다. 복수 owner adoption은 각 owner 준비 결과를 표로 보고, 실패 owner가 있으면 publication을 멈춰 prepared 결과와 원본을 보존한다. 낙관적 CAS를 원격 분산 transaction 보장이라고 부르지 않는다.

### C05. 사용자 면 접촉의 입력·결과·형상 변경 복구

`PRE-CONTACT`의 native3D에서 selection filter=`Face`, 대상범위=`Active Analysis`, setA=`Pad underside`, setB=`Base top`을 선택한다. 목록 Add/Remove, 화면 클릭, tree 선택, Ctrl/Shift와 `Select listed faces` 키보드 대안을 동일 handler로 보낸다. 시안은 A4faces320mm², B2faces336mm², 정확 geometry r12이다. 면 번호 대신 instance/object/subshape와 geometry revision을 저장하며 번호는 표시 보조다.

| 입력/조작 | 형식·unit·기본·범위 | 의존·진단/다음 행동 |
|---|---|---|
| Contact type/law | 지원 enum, 기본 미선택; frictionless/Coulomb/tie/cohesive 중 adapter manifest가 실제 지원한 값만 실행 | 보이지 않게 삭제하지 말고 unsupported row+이유·대안·draft 유지 |
| μ | 무차원 finite ≥0, Coulomb 선택 때 필수. 예시.15는 fixture값이며 제품 default 아님 | frictionless에서는 disabled/display0 convention; tie에는 μ 적용 안 함 |
| Initial gap | 길이/단위, geometry-derived 또는 explicit policy 선택; 시안.20mm | 자동 측정값/설정값 구별. 음수는 initial overclosure이며 adapter 정책/최대허용 명시, 무조건 abs 처리 금지 |
| Normal | geometry-derived oriented vector와 flip action, A→B 화살표 | 노멀 normalization/기저·접촉 convention; flip이 바꾸는 부호와 gap 예측을 미리보기 |
| Search/tolerance/stiffness | 단위·의미·허용범위는 선택 solver law schema에서 제공, 기본 공란/adapter default 명시 | penalty stiffness를 μ와 같은 무차원 입력으로 취급 금지. 숨은 자동 tuning 없음 |
| Interaction step | 정확 step/time interval, sliding finite/small 등 지원 enum | tie와 분리 contact의 계면 의미를 섞지 않음. friction/thermal/damage coupling capability 별도 |

`Validate contact`는 set ownership/empty/overlap/normal/gap·mesh face correspondence·law/element/step/출력 가능성 검사다. `PRE-CONTACT-UNSUPPORTED`는 현재 bounded structural frozen input이 contact를 admit하지 않는 사실과 현재 adapter/runtime 행을 보인다. `Save draft / choose supported adapter / inspect missing capability`를 제공하며 unrelated material/PDE 작업은 계속 가능하다. 등록 capability와 실제 probe, 수치검증 수준은 다른 열이다.

현재 bounded benchmark를 사용자 contact 완료라고 부르지 않는다. 추가 구현은 set→surface export, law cards/friction/gap/normal, compatible mesh pairing, preflight, 실제 결과 parser와 time/association/convention 보존까지다. 면변수·normal이 필요하지 않은 solver라도 UI 의미와 exporter convention의 대응을 명시 검증한다.

결과 `POST-CONTACT`는 exact input r12/run/attempt/result/actualt=.040s를 고정하고 contact pair를 고른다. 압력[MPa] contour, normal force[N]와 tangential force[N] 시간곡선, gap[mm]/penetration[mm]/slip[mm] 선택 표를 제공한다. pressure는 surface/cell/nodal 어디 값인지, resultant force 적분인지 원 solver 출력인지, normal sign convention을 metadata로 보인다. 존재하지 않는 slip 배열은 `NOT_AVAILABLE`로 남긴다. 변형 표시 배율과 contact gap 수치를 혼동하지 않는다. 실패/미수렴 frame은 빈구간이며 성공구간을 보존한다.

저장 후 geometry r13에서 A의1면이 둘로 나뉘고 B normal이 반전된 예시는 `PRE-CONTACT-REBIND`에서 Old ghost와 New를 겹쳐 표시한다. 각 행에는 old/new instance,개수,면적,중심,normal dot,ambiguity,impact(conditions/mesh/results)를 둔다. one→many 선택은 새 두면을 모두 목록에서 확인하고 면적320→319.8mm² 차이를 표시한다. normal dot=−1은 숫자와 화살표를 함께 표시하고 재확인한다. same face number/nearest location만으로 자동 수리 금지. `Preview rebind`는 buffer; `Apply selected`만 새 contact draft 한 변경; `Cancel`은 기존 r12 refs와 r13 unresolved 상태를 그대로 유지한다. unresolved required faces면 run/export 차단, draft save 가능. 이미 계산한 r12 결과는 그대로 reopen한다.

### C06. Post 비교의 연산 순서와 유효영역

기존 pin의 실제 첫 경로는 scalar POINTS, 정확한 같은 mesh 또는 선형 tetra B→A, 동일 unit/metadata/actual time이다. 단위 변환/벡터·tensor 기저/시간보간/다른 element 일반화는 별도 개발이다. `POST-COMPARE`는 각 단계의 현재 capability를 보이며 미지원은 side-by-side 관찰까지 가능하다.

| 순서 | 필요한 결정 | 저장하는 근거 |
|---|---|---|
| 1 | A/B exact result/revision, quantity·measure·location 확인 | arrays/source hashes·공학 의미, Point/Cell/Integration 식별 |
| 2 | 필요한 quantity/단위 변환 | scale/offset·absolute/delta 의미·원값. 변환 미지원이면 차분 차단 |
| 3 | coordinate/basis 변환 | source/target frame, transform, vector/tensor 법칙. scalar엔 불필요한 방향 필수입력 없음 |
| 4 | 실제 time 대응 | exact 또는 명시 linear-common interval; 외삽/gap 금지; 각 값 original/interpolated flag |
| 5 | B→A 공간 대응 | 방법/버전/element/검색 tolerance·포함 predicate·coverage·출발 B cell. 원 ID를 interpolate하지 않음 |
| 6 | 성분 또는 norm, mask intersection | `norm(B−A)`와 `norm(B)−norm(A)` 선택 의미, source/destination invalid 사유 |
| 7 | Δ=B_at_A−A, %=100Δ/abs(A) | 비교식/분모/operation order와 두 mask·각 값 origin |

`delta_valid = meaning_valid ∩ time_valid ∩ spatial_valid ∩ finite(A,B,Δ)`.
`percent_valid = delta_valid ∩ (A != 0) ∩ finite(percent)`.
A=0이면 Δ는 유효할 수 있고 percent만 undefined다. user threshold를0 대신 편의상 epsilon으로 바꾸지 않는다. threshold/near-zero policy 추가가 필요하면 별도 명시 recipe 개정이다. 누락/밖/NaN은 invalid reason과 undefined 값으로 유지하며 통계에는 제외 수·유효면적/점수·선택범위를 보인다. 유효영역 비율만 높아도 중요한 게이지 위치가 밖이면 그 metric은 불가다.

검토 fixture의 affine 식은 s=1mm+x+2y+3z, B=s+.25mm. 내부점의 Δ=.25mm, A=2mm면12.5%; 밖 점은 invalid. 물리값 A0인 별도 scalar fixture에서는 Δ=.25mm/%undefined를 확인한다. 이는 자체 검증 fixture이며 nonlinear 실제 field accuracy 또는 사용자 mapping의 승인이 아니다.

### C07. 같은 내용 이동과 changed-content branch

`POST-REPAIR`/`RECOVERY-REOPEN`은 source별 old path/new path/hash/dependency completeness/affected branch를 보여준다. 먼저 정상 branch와 보존 수치를 연다. `Find replacement`는 승인 root 목록의 파일 선택/등록을 호출하며 ID/URL을 손으로 입력시키지 않는다. chooser를 열었다는 이유로 root 권한을 확대하지 않는다.

동일 파일 내용·지원 의존집합이면 위치 mapping을 새 saved revision에 게시하고 과거 input identity를 유지한다. PVD 한 frame bytes가 다르면 changed row와 영향 time/measurement/comparison을 표시하고 **새 source/input revision 또는 branch**로만 등록한다. 원 ref를 새 bytes로 바꾸지 않는다. 다중 원파일 중 일부만 수리된 경우 정상 branch만 live, 누락 branch는 retained view/미가용으로 남긴다. 현재 Post의 exact VTU/PVD same-content 수리·PVSM rewrite 제한을 재사용하고 일반 reader/변경내용/portable workflow는 추가 작업이다.

Research는 기존 store의 document/revision 형식, Pre는 기존 `.caepre`와 native FCStd/의존세트, Post는 관리 metadata+PVSM+reader dependencies를 사용한다. 이번 설계에서 새 `.caelab` 포맷은 도입하지 않는다. `Open document…`는 type-aware chooser와 최근 문서 metadata로 올바른 owner를 연다. 제품 File association 등록은 승인 후 launcher 과제다. `Save portable copy…`는 기존 형식을 담은 **폴더**에 필요한 등록 artifacts와 manifest를 복사·검증하고 새 문서/store ID의 branch로 연다. 원문서 identity를 두 writable store에 복제하지 않는다. 복사 중 오류면 이전 committed folder/원 store 유지, 부분 folder는 incomplete로 표시한다.

### C08. Evaluation·Runner·remote의 정확한 재개 범위

Evaluation은 **이미 있는** kind=`evaluation`과 같은 editor를 독립/Numerical embedded 양쪽에서 연다. 단계 표는1–32 stable stage ID, saved Material/PDE/Simulation ref, operation/port를 사용한다. 전달/반복 값은 같은 owner; 물리 equation/material/solver step은 원 domain editor. 현 exact_same_mesh metadata 요구와 supported scalar binding을 유지한다.

현재 `thermal.fenicsx.rectangle`→`structural.fenicsx.thermoelastic_rectangle`은 지원 SI path다: metre/global rectangular P1 triangular mesh, steady isotropic uniform Dirichlet thermal field, Kelvin nodal capture, plane-stress free expansion/Tref, bounded lagged Picard/restart_safe. **기존 코드 있음; 이번 실행 안 함.** dimensionless general PDE path나 native C3D10 freeze의 thermal metadata를 이 실제 thermal solver의 대체로 쓰지 않는다. K/°C offset, 다른 geometry/mesh/time/field·stateful constitutive 확장은 별도다.

실제 전달 전에는 `Static connection checked / Actual field pending`를 구별한다. 공급 result를 받은 뒤 required receiver locations/times/measure/units 검사→차단 또는 다음 stage 제출. `NOT_CONVERGED`는 job terminal과 별개이며 solver들이 모두 종료해도 유효 목적값으로 채택하지 않는다. history dependent solver의 반복 trial은 물리 step 시작상태로 restore 가능해야 한다; 그렇지 않으면 feedback capability 차단.

현재 prefix reuse는 **whole definition_sha256와 candidate values 동일**, saved domain refs/출발 inputs도 동일해야 한다. 환경 문제만 고치고 같은 정의로 실패 단계부터 새 attempt를 만들 수 있는 경우만 UI에 enabled한다. downstream stage라도 수정하면 definition hash가 바뀌므로 현재 reuse 불가; `Run changed definition`은 새 입력이다. 유연한 영향 기반 prefix reuse는 추후 명시 확장이고 현재 지원이라고 하지 않는다. 반복은 일관된 checkpoint와 adapter restore capability 없으면 중간 단계부터 이어붙이지 않는다.

Runner close와 cancel은 다른 동작이다. `RUN-CANCEL`은 scope(selected attempt / whole Plan / whole Evaluation), no-new-submissions,현재 child·supports_cancel·last observed·terminal observed를 보여준다. 늦은 결과는 original input/attempt에 남기고 search/next stage를 자동 재개하지 않는다. command_id와 job_id는 각각의 status/cancel endpoint를 사용한다. response lost이면 같은 ID 상태부터 읽으며 새 ID 자동 재제출 금지. service restart에서 추적 끊긴 외부 프로세스는 INTERRUPTED+termination unknown; 같은 workdir 재사용 금지.

remote는 기존 file batch export/import의 frozen candidate/exchange/units/failed/missing 검사를 재사용한다. SSH/Slurm/PBS 자동 지원은 이번 source 범위에서 미확인이므로 분리 backlog로 남긴다. 새 host는 alias/transport/allowed root/queue/resource/credential reference만 설정하고 비밀 자체는 프로젝트·로그·시안에 저장하지 않는다. 전송 전 dependency manifest,원격 job token,결과 hash/partial/staging receipt를 유지한다. disconnect는 remote job cancel 성공을 뜻하지 않는다. `Reconnect read status`→same remote ID 확인→명시 fetch 또는 cancel. 실제 scheduler/requeue 정책 없는 경우 history browsing과 exact numerical resume를 구별한다.

### C09. Study·Expert·기기와 현재 결론

Study는 질문·경쟁 가설·support/refute/neutral evidence·명시 판단·다음 연구를 독립적으로 저장한다. 현재 resolver는 saved document/retained result/saved Expert turn ref를 받는다. literature URL을 직접 기존 ref라고 넣지 않는다. 먼저 Data/document/artifact에 원문+locator/hash를 등록하거나, bounded evidence-reference extension을 구현해 확인한다. 링크열만 있는 가짜 근거 완료를 피한다.

Expert provider 미연결/limit에서는 질문·role·논점·사용자 reply 초안과 과거 실제 발언을 열고 저장한다. `Connect eligible provider`는 실제 설치된 허용 경로 확인에 연결; 별도 유료 API fallback 금지. 개발 Pro relay의 인증/구독은 제품 Expert 권한이 아니다. 생성한 Plan은 사용자 편집 후 명시 실행하고 Study 판단은 별도 채택한다. provider 오류/중지 중 solver가 돌고 있다면 각 상태/취소 범위를 따로 둔다.

기기 직접 제어는 파일 기반 교정의 선행이 아니다. 실제 하드웨어/driver/무료 권한/환경·허용 동작이 있을 때 별도 `DEVICE-PLAN` capability로 연결한다. simulation stop, acquisition cancel, physical emergency stop의 의미를 섞지 않는다. 지정된 실제 환경과 승인 없는 장비 작동은 이 시안에서 하지 않는다. 측정/장착/내구 기준이 없으면 UNKNOWN/NOT_RELEASED를 유지한다.
