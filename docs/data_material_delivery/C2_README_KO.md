# PRO-DATA-MATERIAL-DELIVERY-20261015-01-C2

## 반환물과 소유

Data C1 전용 core를 교정하고, 신규 helper 두 개를 추가했다.
`related_save_recovery_assets.py`는 기존 owner가 인정한 전체 문서와 정확한 source/result/receipt
bytes의 불변 보관 helper다. `data_processing_consumer.py`는 유일한 Data compiler를 기존 Numerical
snapshot/detail/report 입력에서 호출하는 얇은 adapter다. 새 owner/compiler/schema/transaction
engine/후보 evaluator/Qt widget을 만들지 않았다.

`overlay/`는 Data 전용 모듈·관련 시험·예제·문서만 포함한다. 공통 파일은 patch로만 반환한다.
Numerical C1의 전용 파일에는 두 파일의 소비·보존·행 metadata hunk만 별도 patch로 제공한다.
`numerical_candidate_evidence.py`와 CLI는 제공된 Numerical C1과 바이트 단위로 같으며 적용 overlay에
포함하지 않는다. 병행 Numerical C2의 evidence CAS/PRESERVING 교정을 덮어쓰면 안 된다.

원 Data C1 ZIP(sha256 `0c8d82c6e74e84d9f8ecf30bb9ff80172c06f8c3540370d70833999602b59f17`)과
그 원 root patch는 `references/`에 불변 보존한다. 이 폴더는 적용 폴더가 아니다.

## 정확한 기준과 패치 선택

입력 manifest의 current-main은 `26cf0417e78640c3d6a4d36cf7f0a3ac42c3f19e`다.
오래된18bc4fb GUI나 Numerical context 전체를 current-main으로 사용하지 않았다.

| 현재 통합 상태 | Data 전용 | 공통 | Numerical 전용 |
|---|---|---|---|
| 첨부 current-main에 Data initial/C1 미적용 | `overlay/` 추가 | `root-integration-C2.patch` | 승인된 Numerical 원 인도+C1의4개 core가 필요하며 그 위에 `numerical-consumer-C2.patch` |
| 같은 current-main에 Data C1만 적용 | `correction-C2.patch` | `root-correction-C2.patch` | 위와 동일 |
| 같은 current-main에 Data C1+제공 Numerical C1 공통 hook까지 조합 | `correction-C2.patch` | `root-correction-from-composed-C1.patch` | `numerical-consumer-C2.patch` |

각 행에서 한 경로만 고른다. cumulative와 correction을 중복 적용하지 않는다.
Data 파일은 overlay 복사와 correction 중 하나만 선택한다. 위 current-main 밖의 과거 GUI/다른
미커밋 작업 전체 파일을 복사하는 방식은 지원하지 않는다. root가 최신 병행 변경과 hunk를 병합한다.

Numerical prerequisite4개는 `numerical_candidate_detail.py`, `numerical_fit_lineage.py`,
`numerical_candidate_evidence.py`, `numerical_candidate_evidence_cli.py`다. 이것은 **원 Numerical 팀
전달물의 의존성**이지 Data C2가 작성한 후보 엔진이 아니다. `references/`의 공식 두 ZIP과
`NUMERICAL_PREREQUISITES.json`에 출처/hash를 남겼다. already merged 또는 Numerical C2가 있는
저장소에 과거 prerequisite를 덮어쓰지 않는다. 새로운 evidence C2의 파일은 그대로 두고 Data의
전용2개 consumer hunk만 root가 합친다. 새로운 Numerical C2 자체는 이번 입력에 없어 실행하지 않았다.

cumulative root patch는 이전 Data C1과 필요한 공식 Numerical 공통 운반/gate hook까지 합친
현재 main 대비 패치다. C2 순수 공통 교정은 material_document의 정확한 durable hook 및 save 후
working 인정, Workbench 양 carrier 동시 전달 거절, 기존 typed transport 확장 호출이다.
Report/Study 등의 cumulative hunk는 제공된 Numerical C1의 evidence reference 운반/gate이며
Expert/FN32 보고서 엔진을 새로 작성하지 않는다. FN32 gate/이미지 export, DE 기본 예산, 기존 GUI
본문을 유지한다. 공통17파일 cumulative와 순수C2 공통3파일의 차이를 `validation-summary.json`에서
확인할 수 있다.

patch 적용은 기존 root가 `git apply --check` 후 수행한다. 전달 시 세 기준 경로에 각각 실제
적용하여 최종 Data+common+consumer bytes를 검사한 소스와 비교했다. GUI snapshot은 없다.
`tools/verify_c2_delivery.py`는 전달 ZIP 내부 manifest를 읽기 전용 검증하며 저장소를 수정하지 않는다.

## C2에서 고친 실제 동작

Keep 검토는 public 문서와 durable working을 비교하지 않는다. 기존 owner 내부 전체 acknowledged
문서와 durable 파일이 정확히 같아야 하며 saved manifest도 별도 검증한다. runs/display metadata를
임시로 지우거나 draft/run/reference 불일치를 허용하지 않는다. 정상 Material 저장 직후 및 실제
Data import/processing, Plan fit/detail/holdout/evidence/save 이력을 가진 문서에서 Keep가 된다.

capsule에는 raw/local buffer 외에 당시 unsaved 또는 saved acknowledged **전체 base**가 들어간다.
정확한 결과와 source revision, 당시 pending/FAILED/UNKNOWN command·related-save receipt snapshot,
원본 artifact bytes도 검증해 보관한다. peer E2345 저장이나 working 교체 뒤에도 원 E1000 base와
`1e` 원문을 읽을 수 있다. 원 base를 다시 적용하거나 새 saved revision을 만들지 않는다.
readback·부분쓰기·권한 실패는 그 owner의 close를 차단하고, 이미 성공한 다른 owner를 되돌리지 않는다.

Data packet은 기존 한 compiler/validator를 통해 Workbench fit과 Numerical 원 snapshot·selected
detail·holdout·saved evidence·report input까지 이어진다. raw row/derived sample/coordinate/channel,
원 file hash/전체 observation_source hash, signed DAG/value contributor/validity footprint를 구분한다.
reseal한 mask/weight/settings·source 이름 바꿔치기·driver grid/time-unit mismatch·빠진 DAG·dropout
우회·train/holdout raw 공유는 차단한다. legacy NOT_VERIFIED를 VERIFIED로 올리지 않는다.

원 candidate 상세가 없을 때 명시 detail_eval로 별도 attempt를 만들며 원 summary는 바뀌지 않는다.
실패/취소/UNKNOWN 증거는 실패 상태로 남고 success report/adoption gate를 열지 않는다. 기존
Numerical engine의 evaluator/collector/candidate IDs/상한/실패 prefix/선택 attempt 의미는 유지한다.

## 실행한 좁은 검사

전용 시험 목록/실제 pass·skip 수·환경 버전·JUnit·명령은 `validation-summary.json`과 `validation/`에
기록한다. 새 global regression/native solver campaign은 수행하지 않았다.

실제 Workbench와 기존 owner/JobManager를 생성했다. 작은 공개 합성 CSV를 import/apply하고 **실제
owner command**로 sample policy를 채택한 뒤 fit → 원 candidate summary → 명시 detail_eval와
holdout → immutable evidence → report input → save → 한글·공백 경로 이동 → mutable 입력/live
결과 제거 → 새 Workbench와 **별도 Python 프로세스**에서 full DAG/selected detail/raw base 읽기를
실행했다. cold reader는 backend를 등록하지 않고 submit을 금지했다. saved selected detail 파일을
제거하면 실패하며 원 summary로 대체하지 않는다.

이 end-to-end 시험의 평가식은 별도 `test.c2.synthetic`, `P(t)=mu*t`이고 **FELUPE가 아니다**.
material.felupe registration을 교체하지 않았다. 작은 시험은14유효sample, fit7/holdout7이다.
원138sample Windows demo는 불변 canonical compatibility/반례에 사용했으며 **사용자 채택 receipt로
사용하지 않았다**. C1의138sample 실제 owner/JobManager fit·저장·재열기 시험도 별도로 실행했다.

Material 평가 이력의 Keep 시험은 실제 adapter 경계로 들어간다. 이 Linux 환경에서는 FELUPE가
없어 그 평가 실패 상태를 그대로 보존한다. 실제 FELUPE 비교2개는 skip이고 독립 analytic/oracle
검사를 실제 library 실행으로 세지 않는다. 사용자가 보고한 Windows125개 통과 수를 여기에
합산하지 않았다. PySide6/Windows/WSL 런타임 화면은 이번 실행에 없다.

첫 재검사에서 초기 Data-only 시험 하나가 “fit 후보 summary만으로 채택”을 기대했다. 조합된
Numerical C1은 이미 immutable selected evidence를 요구하므로 이 시험은 실패했다. 제품 gate는
그대로 두고 시험을 summary-only rejection 계약으로 교정했다. 실제 evidence/report 성공 동선은
별도의 실제 Workbench 시험으로 확인했다. 실패를 지우거나 수치/성능 기준을 낮춘 변경이 아니다.

## 인수 범위

C01 보관과 canonical 소비의 실제 코드·좁은 계약 검사는 이 패킷의 결과다. 임의 규모의 처리량,
새 수치 benchmark, 모든 원자료 형식, 전체 solver qualification을 주장하지 않는다. portable
writer/GUI/새 Numerical C2의 CAS 교정은 담당 lane과 root가 결합해야 한다. 이미 구현된
PlanVariablesWidget과 Material embed/표준 label을 이 패킷이 다시 구현했다고 표시하지 않는다.

실제 Windows UI에서 pending cell → Keep/부분실패 → 창 유지/닫기 → cold 재열기, 정확한 sample
policy/selected detail 선택을 인수 확인하기 전에는 전체 사용자 인도를 완료로 표시하지 않는다.
