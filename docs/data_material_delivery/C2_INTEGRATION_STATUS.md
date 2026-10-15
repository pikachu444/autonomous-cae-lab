# C2 canonical 소비만 적용

기준 main `b8cf0b63da5ac96eaf705f0dbf99c04104c7415b`. 반환 원본은 `../../pro-received-C2`가 아니라 lane의 `pro-received-C2`이며 ZIP SHA는 MANIFEST에 있다. 원 ZIP·원 patch는 수정하지 않았다.

1. root가 `dedicated-canonical-consumer-b8cf0b6.patch`와 `root-canonical-consumer-b8cf0b6.patch`를 현재 소스에 검토·적용한다. 두 패치는 서로 다른 파일이다. `overlay/`에는 두 패치 결과 파일을 그대로 보관했다. 전체 overlay를 덮어쓰지 않는다.
2. 전용 제품 변경은 `data_processing_consumer.py` 신규, `data_processing_lineage.py`의 signed/value-validity footprint/driver 검증 보강, `data_processing_selection.py`의 원 header/trial 보존이다. 나머지 기존 Data 처리/서비스/혼합제어 모듈은 main 유지한다.
3. 공통 9파일: `assist/experts.py` typed fit transport 확장; `evaluation.py` derived sample 선택/페이지; `identification.py` canonical independence 검증; `material_test.py` frozen coordinate driver 정렬; `numerical.py` sample weight·canonical packet 실제 fit·결과 보존; `numerical_document.py` processing resolver·명시 sample policy·driver binding·freeze; `workbench.py` resolver 주입·canonical/legacy 동시 인자 거절; `numerical_candidate_detail.py` admission·immutable snapshot·table metadata와 null transport 1회 처리; `numerical_fit_lineage.py` 기존 Data validator 소비.
4. 공통 3개 겹침은 세대/의미 변경 없이 원 Pro 추가를 유지했다: Numerical result의 frozen packet, Numerical draft의 selection+extensions 허용, Workbench의 canonical/legacy 충돌 guard. CRLF가 섞인 원 patch를 private scratch에서 LF로 정규화하고 3way 병합했다. engine 알고리즘을 Codex가 새로 작성하지 않았다.
5. `material_document.py`의 C01 acknowledged/save durability hook, recovery modules/HTTP action, host close hook은 이번 패치에 없다. 미저장 Data 등록 원자료 closure 누락은 실제 Pro C3 작성 중이며 C01은 NOT_INTEGRATED다.
6. main `plan_variables_api.py`의 Redo는 untouched. Numerical detail `_record_capture_publication` import/call 2줄은 현재와 merged에서 동일하게 유지했다. evidence.py/CLI, related-save modules·lost-ack GUI, RawFocus guard, 다른 GUI/Expert/FN32/DE/M4/portable는 patch 대상이 아니다. report/Study transport는 이미 main의 Numerical C2이므로 원 누적 patch를 다시 적용하지 않는다.

검사 파일은 Pro 원문 `test_c2_compiler_consumer.py`, `c2_fixtures.py`, `helpers.py`와 두 공개 demo JSON만 분리했다. test의 bound fixture는 실제 Data import/processing owner를 쓰고 compiler-only fixture는 사용자 채택 receipt가 아니다. `test_c2_workbench_chain.py`는 recovery까지 합쳐져 있어 이 조합에는 포함하지 않았다. 원 Pro Linux 163PASS/2skip은 현재 Windows/NumC2 composition의 검사 결과가 아니다.

Codex 확인: 원 archive/94 manifest hash·AST 파싱·private exact-base 적용·보호 hook·최신 main 동일파일 hash. 새 runtime/Qt/native/solver 실행은 root RAM 제한으로 0회. 이후 허용된 최소 검사는 아래처럼 분리한다.

- canonical admission 반례: Pro compiler consumer 검사만(원 source/driver/grid/unit/mask/weight/누출/header/legacy 동시 인자).
- 실제 owner 동선: 공개 tiny Data 처리→명시 sample policy→Plan fit→선택 detail/holdout→정확 evidence 저장→cold. P(t)=mu*t test backend는 FELUPE 비교가 아니다.
- 보호 회귀: 기존 Numerical C2 saved-publication CAS/Plan Redo/related-save lost ack는 관련 기존 검사만 재사용한다.
- C01 raw Keep/close/portable 복구는 C3 source 검토·통합 이후 별도 진행한다.
