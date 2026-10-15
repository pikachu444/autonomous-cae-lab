# 구현 접점·소유·보호

## 전용 구현

`caelab/portable_research_knowledge.py`: 선언된 Study/Expert draft·Undo/Redo·turn·round·실행 인자/결과·Co-STORM 보고서/부분 journal·Report frozen A 및 원 owner archive의 exact knowledge pins를 수집한다. 기존 KnowledgeStore.source/check_access를 거쳐 원 raw bytes와 segment metadata의 검토 fingerprint를 만들고 발행 때 재검사한다. index/search/extraction 없이 기존 KnowledgeStore 경로에 보존 개정과 선택 구간을 반입한다. `archived_source/revision_details`는 기존 source payload를 유지하고 원/현재 정책을 분리한다. A/hash/citation 원값은 재작성하지 않는다.

`caelab/portable_research_owner.py`: S/X 원 saved+ack/실행 기록을 기존 portable_execution archive·TypedProjection으로 보존한다. logical run/원 rounds/turns 해시를 재검증한다. 현재 draft의 원 transmission_scope/Co-STORM/session 권한은 제거하되 원 raw archive는 변경하지 않는다. 원 시도와 current live rounds/turns를 분리하고 현지 command와 결과에만 기존 completed-job harvest를 허용한다. 새 command가 원 job에 연결되지 않도록 owner/request/operation/arguments를 검사한다. `command_response`는 기존 현지 영수증을 재실행하지 않고 현재 읽기 권한만 재검사한다. 원 증거의 현재 탐색은 typed map을 통해 별도 표시하며 원 제출 인자와 hash는 그대로다.

`apps/research/portable_research_actions.py`: 기존 Study/Expert 파일 메뉴, 명시 Save/보관본만/Cancel 대화, 기존 ConnectionWindow, 다음 현지 역할의 명시 진행, 원문 metadata/위치 표시를 연결한다. 복사 선택에서 edited_draft나 apply를 몰래 호출하지 않는다. helper가 만든 자식 창만 닫는다.

`apps/research/portable_research_report.py`: 기존 Report 원문 읽기와 내보내기의 현재 권한·current owner·선택/늦은 편집 검사. 권한 거부 시 과거 민감 미리보기만 제거하며 R1 이미지 누락 미리보기는 유지한다. 기존 renderer/atomic_export를 호출하며 새 출력 엔진을 만들지 않는다.

`examples/portable_study_expert_public.py`: 실제 S/X/B owners, 공개 Markdown 2개정, frozen A raw bytes, 원 성공/실패/READY 기록, 미완성 질문, 새 명시 controlled Ask, 두 독립 process cold/재복사의 재현. generation 및 dependency discovery만 labelled double이며 새 provider를 설치/호출하지 않는다. Co-STORM 전용 tests는 실제 vendored runner의 진행/map/report/journal을 사용하고 generation 및 exact retrieval만 명시 double로 둔다. 검색 ranking/Haystack/실제 AI 자격 검사가 아니다.

## 기존 API 유지

WorkBench의 `portable_inspect/portable_copy/portable_verify`, `document_read/document_command/document_result`, `study_references/research_reference`, `report_capture/report_content`, `assistance_call('knowledge.source', ...)`를 그대로 사용한다. 새 service/HTTP endpoint/document owner/registry가 없다.

사본 manifest에는 기존 format을 확장하는 `knowledge_revisions`, `knowledge_workspace_id`가 들어간다. 현재 S/X에 `portable_research_owner`, X에 `portable_expert_history` 및 권한 분리된 read facet이 추가된다. 현재 Report의 `portable_knowledge_refs`는 현재 섹션/Undo에서 사라졌어도 원 raw owner archive에 남은 exact 원문 closure를 재복사하기 위한 선언이다. 이 필드는 새 권한 grant가 아니다.

`research_reference(knowledge)`의 기존 source payload shape와 hash를 유지한다. `source_metadata`는 바깥 읽기 응답의 별도 필드다. 원 title/collection/locator/선택 text는 hash 비교 대상 그대로이며 현재 role의 collection 검사에는 현재 KnowledgeStore 정책을 사용한다.

원문이 없지만 frozen 읽기 권한은 유효한 Report는 기존 `source_status=UNAVAILABLE`, `navigation_status=SOURCE_UNAVAILABLE`, `navigation_reference=None`을 유지한다. 현재 scope 자체가 불충분하면 `snapshot_status=SCOPE_REQUIRED`이며 frozen content를 반환하지 않는다. 원 store fallback은 없다. 이 두 상태를 같은 자료 누락으로 병합하지 않는다.

## root-only shared 통합

아래 파일의 필요한 hunk만 integration.patch에 포함한다. shared 전체 소스 사본은 인도하지 않는다.

- Knowledge/권한: `caelab/assist/knowledge.py`, `assist/experts.py`, `research_workflows.py`, `workbench.py`.
- 기존 owner/보존: `study_document.py`, `discussion_document.py`, `discussion_costorm.py`, `material_document.py`, `report_document.py`, `report_image.py`.
- 기존 portable 계약: `portable_project.py`, `portable_project_drafts.py`, `portable_project_execution.py`, `portable_project_report.py`.
- 기존 GUI host: `apps/research/study_window.py`, `expert_window.py`, `connection_window.py`, `reference_content.py`, `report_window.py`.

root는 현재 WIP와 좁은 hunk를 대조하여 통합하고 Sol은 실제 Windows GUI를 확인한다. 해당 패치는 baseline을 덮어쓰는 전체 파일 인도가 아니다. 전용 신규 파일·tests/docs는 product.patch와 source/에 있다. 공유 Python의 원 EOL을 보존하고 before/after bytes·SHA256를 SOURCE_CHANGES.json에 기록한다.

## 보호 범위

FN05의 selected_problem/최종 진단·Data admit_snapshot/retained_assessment 및 두 canonical submitted hash/inputs hash 계산 코드는 변경하지 않는다. native helper, upstream pin, 라이선스/notice, solver, B13/PDE/Contact/finite-measure/Impact A/B/C/Data·Runner GUI도 변경하지 않는다. R1 원 A JSON/PNG/raw owner archive·P2 current navigation 실패 처리·한국어 기존 화면을 보존하며, 문헌 권한 거부에 필요한 Report cache/export hunk만 별도 추가한다.

새 ACL/권한 승인 화면·검색 index·scheduler·server·document store·solver·유료 의존·schema framework는 없다. 보존 archive/typed 읽기 바인딩은 기존 portable ownership과 KnowledgeStore에 한정한 좁은 확장이다.


## 현재 D 공개 문헌과의 통합

`portable_research_knowledge.evidence_pin/collect_literature/write_literature`는 기존 Literature.read의 정확한 content-addressed archive·locator·서지/읽은 범위 검사를 재사용한다. 선언된 `paper_id` 인용과 Co-STORM state/retrieval_journal 및 완료된 retrieval_operations의 read 결과만 dependency로 취급한다. 토론의 원문/원 locator는 재작성하지 않는다. JSON 및 선언된 추출 원문 bytes만 기존 literature 폴더로 검증 복사하고, mutable papers.json·인증·설정·검색 index는 옮기지 않는다. manifest의 `literature_archives`와 기존 immutable files 목록으로 새 위치의 bytes를 다시 검증한다.

현재 owner의 `literature_access`는 Workbench가 연결하는 기존 Literature.read callback이다. archive 읽기에 새 외부 검색/전송 grant는 없다. 새 Ask의 글로벌+요청별 공개 검색 허용·참여 role 도구·도구예산·취소 및 중단 성공분 재사용은 기존 D 계약을 유지한다. 공개 검색 실패나 abstract-only를 full-text로 승격하지 않는다.

Report의 과거 saved base를 수집할 때는 해당 개정 폴더의 원 A와 navigation proof를 검증한다. 같은 A identity를 쓰는 현재 owner의 다른 proof를 과거 개정에 적용하지 않는다. 검증 관문/원 hash/bytes와 원본 archive는 유지한다.


Ask 전 질문/Undo 및 사용자가 남긴 발언의 명시 `paper_id` evidence도 같은 보관 인용 closure에 포함한다. 공개 paper는 CAE 문서 owner가 아니므로 document-ID mapping을 적용하지 않고 원 paper_id/locator/서지/읽은 범위를 그대로 보존한다. 새 검색·새 grant·원 발언 재작성은 없다. 잘못되거나 없는 archive는 기존 검증으로 복사를 차단한다.
