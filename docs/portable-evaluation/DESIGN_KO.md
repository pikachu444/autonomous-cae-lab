# Evaluation 이동 사본의 경계

CB06은 기존 portable project와 EvaluationDocuments, execution proof, 단계·전달 reader를 연결한다. 새 store, job manager, solver, schema 또는 문서 owner는 추가하지 않는다. 기존 C3B owner 계약과 [portable physics](../portable-physics/DESIGN_KO.md)를 따른다.

`portable_project_evaluation`은 다음을 담당한다.

- 기존 `write_execution`으로 원 input/job bytes 및 결과 digest와 원 run을 보존하고 기존 TypedProjection으로 이동 관계를 재검증한다.
- Evaluation prepared arguments의 정확한 `definition`, `snapshots`, `definition_source`만 투영한다. snapshot은 선언된 단계 참조와 `verify_reference`로 일치해야 한다. 임의 문자열·경로·응답·숫자에는 치환을 하지 않는다.
- 현재 문서의 `stage_inputs.json`과 `_stage_snapshots`는 참조한 단계 원문서의 검증된 compact input으로 새 owner에 연결한다. 원 stage input 파일은 portable originals에 그대로 보존한다.
- 원 result/progress/stage folders, attempt ID, transferred field/receipt, model input, 실패·UNKNOWN·재사용 prefix는 원 bytes로 유지한다. 복사된 job을 현재 manager에 등록하지 않는다. 보존 상태는 exact retained job에서 읽는다.
- 최종 부모 result 없이 terminal 실패한 실제 progress/완료 stage도 기존 revision/results에 보관한다. 기존 save가 한 번 읽은 동일 job/source를 Evaluation 전용 helper에 넘겨 상태 판정과 파일 보관을 묶는다. 없는 최종 result나 aggregate 응답은 만들지 않는다. 그 원 기록이 없을 때의 실패 의미와 기존 재사용 참조 조건은 유지한다.
- 전달 reader는 이동 증거가 있는 경우 원 definition으로 원 receipt를 비교한다. current owner/선택 탐색은 사본을 가리킨다. 다른 source ref나 손상된 field를 허용하는 우회는 없다.
- 명시적인 새 `evaluation.run`은 현재 owner가 다시 준비·검증한 입력으로 기존 실행기를 호출한다. 재사용은 원 결과/정의 hash와 증거로 확인한 current definition 전체가 일치할 때만 읽기 전용 비교 뷰를 만든다. 기존 evaluator의 values와 각 bound stage model hash 검사는 그대로다. 이 뷰는 원 결과를 수정하거나 새 계산 결과로 저장하지 않는다.

현재 문서 수정·Undo·저장·재복사는 재계산하지 않는다. proof를 포함한 owner save와 재열기는 기존 immutable revision, CAS와 복구 절차를 이용한다. native 경로·승인·권한은 보관 provenance이며 현지 실행 권한으로 승격하지 않는다.

범위는 기존 Evaluation의 모든 선언된 Material/PDE/Simulation stage backend다. 실행 가능 여부는 기존 adapter/runtime gate에 남긴다. iteration/lag/shared input/adjoint가 포함된 원 선언과 결과도 동일한 보관 규칙을 쓰지만 이 인도의 실제 계산 확인은 공개 S1 uniform의 서로 다른 P1 메시 온도→열변형 한 경로다. 모든 backend 또는 반복·adjoint를 새로 실행해 검증했다고 주장하지 않는다.

공개 실행: `python -m examples.portable_evaluation_public --output <새 폴더>`.
전용 검사: `python -m pytest tests/test_portable_evaluation_documents.py -q`.
Windows 검증은 `scripts/native_check.py`로 소유한 프로세스와 자식을 정리한다. 실제 결과·사진·파일 manifest는 `_workspace/delivery-portable-evaluation/`에 남긴다. 원 실패와 fixture 교정 기록을 삭제하지 않는다.
