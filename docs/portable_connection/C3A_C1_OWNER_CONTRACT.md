# C3A02 C1 — Q 의존 참조와 전체 문서 재시도 계약

요청: `PRO-PORTABLE-CONNECTION-20261015-C3A-02-C1`. 원 C3A02 인도에 대한 증분이다. C3B나 전체 C3 완료가 아니다.

## Q 의존과 시작 개정은 별개다

`inspect_copy`는 명시 Q 수집을 기존 revision 순회 **앞**에서 수행한다. `seed_dependencies`는 이미 검사된 acknowledged 전체 문서의 `document_references(include_history=True)`와 `comparison_references`, 보관 당시 saved base를 순회의 seed로 추가한다. 새로운 ID 탐색기나 store는 없다.

선택한 Material R1과 두 Plan R1은 여전히 새 편집 owner의 시작 저장본이다. Q에만 있는 Material R2/I2는 별도 exact revision/input 대응을 받는다. 동일 입력을 다시 저장한 R2b가 있어도 명시 R2를 R2b로 바꾸지 않는다. `saved_only`는 현재 working을 제외하는 선택이지 명시 Q의 과거 의존을 버리는 선택이 아니다. `acknowledged`에서도 Q 이후 Undo·분기 편집으로 현재와 이력에서 사라진 참조를 보존한다.

Q의 saved_sources는 기존 `inspect_capsule`, owner fingerprint, `verify_snapshot/verify_assets`가 검사한 실제 자료이다. 선택 owner의 과거 revision 폴더가 없으면 그 Q.assets를 기존 AcknowledgedReader의 읽기 위치로 사용한다. 실제 live revision이 있으면 서로 같은 원문/manifest인지 확인한다. 손상된 live revision을 Q로 몰래 수리하거나 현재 값으로 채우지 않는다. Q assets가 부족하면 정확히 실패한다.

peer owner는 반드시 사용자가 함께 선택해야 한다. Q에 bytes가 들어 있어도 새 편집 owner를 자동 포함하지 않는다. 여러 Q에 같은 saved identity가 있으면 서로 일치해야 한다. 중복 Q 선택은 기존 규칙대로 실패하며 어떤 정상 Q도 지우지 않는다.

`_Fork`는 같은 검증을 다시 수행하고 기존 transfer_map/TypedProjection과 revision writer를 사용한다. 매 hop의 acknowledged typed dependency가 존재해야 발행·재개 검사를 통과한다. 원 Q/ack/raw/receipt/result의 bytes와 원 identity는 바꾸지 않는다. 기존 결함 사본의 Q 자체가 유효하면 original layer 읽기는 남기되, 불완전 mapping을 READY/BUFFER_READY로 승인하지 않는다.

## 미적용 raw는 증거가 아니다

raw text와 local_draft의 임의 ID/path는 closure를 확대하지 않는다. 원 acknowledged와 같은 typed binding을 상속한 local_draft 경로만 별도 navigation projection한다. 원 raw에서 달랐던 binding은 모든 hop에서 미적용 원문으로 남는다. 숫자·빈칸·`1e`·`invalid`를 parse/apply하지 않는다. 사용자 신규 raw binding은 현재 owner의 기존 명시 편집/연결 검증을 거쳐야 한다.

원 Q의 read와 현재 owner의 UPDATE·save·새 Keep는 다른 행위다. old Q를 `raw-recovery/`나 commands에 설치하지 않는다. 원 recover/discard/store/session/command 권한은 `NOT_GRANTED`다.

## 응답 유실과 전체 acknowledged 상태

기존 MaterialDocuments의 UPDATE/Undo/Redo response receipt에 `acknowledged_document_sha256`을 추가한다. 이것은 공개 UI projection이 아니라 그 command가 실제 확정한 내부 전체 문서의 canonical hash다. 기존 `_mutation_command`에는 그 marker 자체를 제외한 전체 문서 hash를 추가한다. 기존 `recover_mutation`이 receipt 응답 쓰기/메모리 대입 전 유실을 복구할 때 이를 대조한다. 새 journal이나 owner를 만들지 않는다.

Portable resume은 새 command일 때 원 review의 target identity 및 전체 acknowledged hash를 확인한다. 같은 command가 이미 있으면 기존 owner의 receipt/확정 mutation 복구를 먼저 사용하고, 반환한 전체 post-state hash와 현재 `acknowledged_state` 및 public document가 모두 일치해야 raw buffer packet을 반환한다. 단순 input identity 일치는 충분하지 않다. 실제 material.evaluate는 input identity를 바꾸지 않고 runs를 추가할 수 있다.

비교 보존도 확인한다. 첨부 기준의 실제 `retain_comparison`은 input_revision을 유지하지만 generation을 올린다. 이를 input identity 전체가 같다고 주장하지 않는다. runs·comparisons·title·미공개 Undo/Redo·알 수 없는 owner 필드·다른 no-op mutation 모두 현재 문서 변경으로 취급한다.

진짜 같은 preview/command/session/buffer의 응답 유실은 같은 결과로 재시도한다. 다른 buffer/session/Plan 또는 이후 문서 변경에는 오래된 `response.document`를 반환하지 않는다. GUI는 실패 시 현재 화면/미완성 buffer를 보존한다. 이미 서버에서 반영된 command를 취소됐다고 표시하거나 자동 새 command를 발행하지 않는다.

C3A02 이전 receipt에 전체 post-state 증거가 없으면 C1이 그것을 추정해 추가하지 않는다. 이 경우 과거 receipt를 성공 재시도로 승격하지 않고 원 preview/raw/현재 문서를 보존한 채 거절한다. 새 검토는 사용자가 명시적으로 선택하는 별도 동작이다. 새 C1 command의 정상 유실 재시도와 durable-write-before-memory 유실은 실제 회귀 대상이다.

## 통합 소유권

전용 코드: portable_project, portable_project_drafts, portable_project_recovery, portable_recovery_resume, portable_recovery_dependencies. 공통 변경은 `material_document.py`, `related_save_edits.py`의 작은 hunks뿐이다. product.patch와 integration.patch를 한 쌍으로 적용한다. 기존 C3A02 patch를 다시 적용하지 않는다.

Sol의 손상 Q 선택/주화면/원문 위치·선택·포커스 GUI 파일은 변경하지 않는다. 새 Material law/native, FE/PDE/Post/R2/Report 코드는 변경하지 않는다. root는 현재 main/WIP에서 이 hunk만 통합한다. Windows/Qt/native와 현재 main+병렬 WIP 적용 검사는 별도 NOT_RUN이다.

C3B Report/Study/Expert/PDE/Simulation/Evaluation 및 managed FCStd/Post 이동·cold·재복사는 필수 후속이며 이번 수정에 포함되지 않는다.
