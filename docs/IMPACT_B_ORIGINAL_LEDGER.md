# 원 Impact B ledger — 요구 삭제 없음

**인도 상태: PARTIAL_B_IMPLEMENTATION. 전체 B 완료 아님.** 기준은 직접 제공된 `references/ORIGINAL_B.md`, `request/REQUEST.md`, `request/ACCEPTANCE.md`다. 원문을 반환 ZIP `basis/`에 변경 없이 보존한다. 원 A/C 범위는 별도 작성자와 통합해야 하며 본 인도에서 완료하지 않았다.

## 의존과 작성 단위

B1은 A가 검사한 effective mesh/part/material/property와 기존 LAW36 hardening 위에 전용 INIEVO 카드·교정·길이·결과를 추가한다. A의 일반 계층 INP/native RAD·source compiler를 대체하지 않는다. B2는 기존 LAW117/geometry 위에 정확한 대향 bulk면·TYPE24 명시 활성·삭제 전후 선택을 연결한다. B3는 B1/B2의 원 입력·카드·terminal·raw identity를 고정해 같은 owner에서 실패 readback·보존·새 process 재열기를 수행한다. native/physical acceptance와 Sol의 Qt 화면 통합은 별도 의존이다.

| 원 조건 | 실제 작성/실행한 항목 | 남은 수용·범위 |
|---|---|---|
| B01 벌크 조합 | `impact_bulk`, `impact_bulk_deck`, facade/adapter 최소 hunk. 실제 pinned Python converter와 원 postflight에서 LAW36·Isolid24·1 IP·FAILIP1, exact FAIL/INIEVO·TABLE/1·TH/BRIC 생성/재검증. 기존 LAW117와 추가 FAIL 범위 분리. | Windows Starter의 카드 수용·Engine 실제 native 조합 NOT_RUN. affine C3D8/R 외 formulation/IP, multi-rate hardening, native RAD 직접 경로는 미완결. |
| B02 Gf·길이·범위 | ILEN0, initial affine V/L0 예측, Gf N/mm, INITYPE1 eta/(EPSD/SR_REF), raw eta와 native clip, 온도 교정 metadata, source의 factor2 reference 함수. 1/2요소와 출력/CFL 비교 입력 생성. | native 초기 VOL 및 L0 일치, unique initiation/evolution 상태 출력, onset YLD0·실제 stress softening 검증, 시간/mesh 에너지 수용 NOT_RUN. 크기 객관성·소산량 인증 없음. |
| B03 UNKNOWN·초안 | 필수 교정 빈 기본값, positivity/shape/range/error 검사, 잘못된 FAIL/원 카드 변조·교정 불일치 차단. 기존 owner의 미완결 초안 저장 검사. | 실제 Qt의 오류 위치 수정·표 편집·취소 동작은 Sol 연결 필요. 원 교정 없는 물리 승인은 계속 UNKNOWN. |
| B04 계면 전체 이력 | 기존 LAW117 카드/envelope 보존. COHESIVE_ONLY와 명시 delayed TYPE24, exact 대향 bulk면·alias/중복 검사, 활성시각 카드 수정, 표본 기반 deletion 조건 위반 감지. | **부분 손상 0<d<1 loop와 mixed mode, 압축 이중계상 방지의 연속 native 검증, 완전삭제 뒤 실제 recontact/reopen 미완결.** 자동 deletion-triggered contact가 아니며 clock gate의 표본 관측만으로 완료하지 않음. 2612 확장 Isym/criterion/evolution 편집도 잔여. |
| B05 pair·active | 원 TYPE24/member/group/FNFT identity와 원 stored values 보존, bulk OFF와 geometry masks, missing≠deleted. cohesive 삭제 뒤 살아 있는 bulk pair의 기하 선택. | exact native contact penetration·normal reaction·cohesive traction 선택, FNFT native 저장량의 force/impulse 생산경로 검증 미완결. 물리 pair 응답 UNKNOWN. |
| B06 impulse·clock | actual binary32 TH 시각, source rows/byte ranges, 독립 frame ordinal·gap, sampled trapezoid의 sign/비등간격/gap 거절. 기존 all-contact nodal 응답과 pair 구별. | 정확한 native pair impulse/force와 converter 미분 여부 수용 미완결. sampled integral은 solver 전체 증분의 정확한 충격량 아님. |
| B07 에너지·질량 | TH/BRIC IE를 density로 읽고 DAMA와 OFF 분리. global IE/KE/contact/hourglass/external work/plastic work/MASS/ADDED MASS 개별 보존·단위 환산. | native bulk/interface damage-dissipation 고유 채널과 original mass의 직접 관측 미수용. 합산·차감으로 생성하지 않음. 실제 에너지 회계/민감도 판정 NOT_RUN. |
| B08 실패 재후처리 | Radioss 전용 immutable terminal·raw pin, complete TH/CSV prefix, 손상 tail 기록, 독립 VTK와 gap, 원 실패 보존, 새 derived. 원파일/record 바뀜 거절·no native/provider call·원본 불변 검사. | native 실행 중 fail/cancel로 생성된 실제 Windows raw와 큰 파일에서 수용 NOT_RUN. raw ANIM-only는 자동 변환하지 않음. native 성공 로그만으로 sample coverage를 완전으로 만들지 않음. |
| B09 저장/cold | 기존 Simulation/JobManager의 원 FAILED→저장 revision→명시 새 readback→선택 곡선 저장→mutable 결과 제거→새 Python owner 재열기 실행. 물리 입력 변경 거절, 선택/metadata/raw assets 보존. | 합성 raw fixture 경로의 성공이다. Windows native 계산에서 온 동일 작업의 Qt 저장/reopen 및 실제 화면 선택·다른 도구 return은 남음. |
| B10 전달 | 신규 source/tests/examples/docs, product.patch와 A/root 최소 hunk, before/after 파일목록, exact baseline patch roundtrip, 실행 로그/NOT_RUN/원 요구·라이선스 제공. | 부분 인도의 회수 조건이다. 이 행의 인도 성공으로 B01–09의 native/물리 잔여를 완료 처리하지 않음. |

## 원문 문단과 대응

원 B 첫 문단(첫 벌크 native 조합·대안·정규화)은 B01/B02에 유지한다. 둘째 문단(교정·속도·삼축도·softening/state/active/에너지·비교)은 B02/B03/B07에 유지한다. 셋째 문단(LAW117 부분/완전삭제 반복 이력·contact·선택)은 B04/B05에 유지한다. 마지막 문단(pair/impulse/mass/energy/failed readback)은 B05–B09에 유지한다.

native LAW36+INIEVO가 불가능하다고 판단한 것은 아니다. source hook과 작은 변환 경로를 실제 연결했고 native runtime 조합 수용은 미실행이다. 불가능하다는 근거 없이 다른 법칙으로 바꾸지 않았다. 현재 조건을 넘어서는 요청을 자동 축소해 성공 처리하지 않는다.

## 타 팀 보존

공유 변경은 `impact_model.py`, `adapters/impact.py`, `simulation_document.py`, `workbench.py`의 작은 접점뿐이다. A의 source/model/native compiler·admission/일반 reader 전체 파일을 반환하지 않는다. 기존 LAW117/impact_responses/impact_results/impact_timing은 원문 그대로다. C 피로, Sol 화면, Data/Runner의 후속 표시, C3B Report, B13/Contact/S2/finite의 소스에는 변경을 넣지 않았다.

기준 ZIP 이후 커밋이나 private/WIP를 읽거나 통합했다고 주장하지 않는다. 후속 main 위에는 manifest의 before SHA와 접점을 대조해 root가 hunk를 정합해야 한다. 자동 force 적용이나 보호 파일 덮어쓰기를 제공하지 않는다.

## 2026-10-16 현재 main 통합 경계

원 Pro의 B01–B10 요구와 위 잔여를 유지한다. 전용 벌크·계면·TFILE/4 읽기19파일을 재사용하고, 최근 A의 보존 결과 읽기·원 슬롯/부분 prefix 보호를 이전 B 재후처리 파일로 대체하지 않는다. B08/B09의 반환 당시 합성 실행과 별도로, 현행 Windows owner의 B 추가 선택·정의 pin·실패 부분 읽기·저장·새 Python cold 읽기를 합성 입력으로 확인했다. B 정의가 없는 과거 작업은 UNKNOWN이고, 정의 pin 변조와 없는 채널은 성공으로 바꾸지 않는다. 원 작업 실패도 그대로다. 원문 변경 뒤 재료 적용집합·논리 요소·접촉쌍의 원 대응 변경은 기존 검토/명시 적용을 거쳐야 한다. 이 연결 및 국소 확인은 실제 native B 물리 수용이나 전체 B 완료가 아니다.
