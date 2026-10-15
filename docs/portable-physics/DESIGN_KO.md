# 이동 가능한 PDE·Simulation 실행 기록

기준 de7de4e, upstream 3e48bf6138f495299f45b1af254bfb4aaff307b8. B8.3/CB04·CB05의 기존 확정 설계에 따른 Sol 구현이며 새 Pro 설계를 만들거나 별도 owner/DB/solver를 추가하지 않는다.

## 구현과 공통 접점

전용 `caelab/portable_project_physics.py`는 기존 `SnapshotReader`/`AcknowledgedReader`가 읽은 원 실행을 검사한다. kind에 맞는 실제 `pde.evaluate` / `simulation.run` / 보존 `impact.reprocess`, 원 draft/hash·중복 backend/settings, terminal 보존 여부를 확인한다. 기존 `write_execution`의 원 input/job bytes, `TypedProjection`/source scope/입력 대응 및 결과 digest를 그대로 사용한다. 원 field/input/실패 파일은 기존 결과 저장 디렉터리의 선언된 asset이며 새 format으로 재구성하지 않는다.

새 local run은 기존 owner.command → JobManager → 평가기를 사용한다. 원 실행 read facet과 현지 입력/새 작업을 분리하며 원 command/session/운영자 설정을 현지 실행 권한으로 설치하지 않는다. copied jobs를 controller queue에 등록하거나 자동 harvest/retry하지 않는다. `read_execution`은 기존 owner의 읽기 결과와 원 제출 입력을 검증해 돌려주는 함수이며 submit/command/manager를 제공하지 않는다. 새 endpoint나 두 번째 owner가 아니다.

root 통합 최소 접점은 다섯 파일이다.

- `portable_project.py`: supported kind/prefix, 전용 검사/쓰기/boot 검증 hook. 기존 staged copy, source 재검사, last manifest, exclusive publication은 유지한다.
- `portable_project_execution.py`: PDE/Simulation typed kind와 명시 operation 인자. 기본 fit/detail_eval 계약은 그대로다.
- `pde_document.py`, `simulation_document.py`: 기존 public execution 읽기와 save proof retention hook. 기존 draft·command·평가기와 `simulation.reprocess` 관문은 유지한다.
- `apps/research/pde_window.py`: 기존 File 메뉴의 동일 copy helper, 상속 Simulation, accepted-close 때 helper 소유 자식만 정리. 기존 한글 plot font 설정 재사용. 결과 없는 보존 종료 실행은 원 상태·오류로 표시하고, 보존 결과 읽기 오류를 live 원 job 조회로 대체하지 않는다. 이전 성공 화면도 기존 초기화 경로로 지운다. 새 현지 pending job의 상태 조회는 유지한다.

공통 변경은 `_workspace/delivery-portable-physics/integration.patch` 및 추가 표시·보존 실패 읽기 patch로 root에게 제출해 root가 반영했다. 공통 copy 선택창의 안내는 질문/판단 대신 ‘편집한 내용’으로 중립화했다. 전용 작성자는 공통 파일을 직접 덮어쓰지 않는다. Data/Material/Numerical/Study/Expert/Report, D 공개문헌·권한·Co-STORM retry 코드는 보호한다.

## 원 값과 실패 경계

copy writer는 원 실행 기록과 결과 bytes를 archive에 남기고, 현지 읽기 참조에만 검증된 새 owner/input identity를 사용한다. 새 입력으로 편집한 원 결과는 `is_current_input=False`다. 재복사 시 이미 있는 proof의 lineage를 이어 검증하고, 현지에서 새로 실행한 job은 그 계산의 별도 origin을 갖는다. 하나의 문서에서 두 origin이 보이더라도 결과/입력을 합치지 않는다.

현재/원 input hash·backend/settings가 불일치하거나 원 job/status/error/result/proof/field가 없거나 변조되면 거절한다. 원 proof 없는 legacy derived run은 새 계산으로 승격하거나 자동 재바인딩하지 않는다. 새 미완성 draft는 원 결과와 독립적으로 저장할 수 있고 기존 diagnostics가 평가를 차단한다. runtime 부재의 새 실패는 새 job으로 남고 원 성공 결과는 계속 읽을 수 있다.

## 다음 인도의 정확한 접점

CB06 Evaluation은 stage/attempt/transfer/reuse prefix의 exact provenance를 이 원 execution proof/read source에 연결해야 한다. 현재 CB04/05 구현이 Evaluation의 외부 reference를 임의로 수집하거나 실행하지 않는다.

CB07은 `.caepre`/FCStd/native Analysis/XLink·현재 native registrar를 별도로 보존·검증 이동해야 한다. `structure.calculix.design`의 data_id/source_sha256/recipe는 원 기록으로 유지하며 새 위치의 registrar/runtime으로 자동 대체하지 않는다. 원법칙의 source_guard는 provenance이며 이전 경로를 새 live 권한으로 바꾸지 않는다. inline INP/RAD/mesh/field/source text를 보존하는 것과 live native owner를 재개하는 것은 다르다.

CB08은 원 Post project/PVSM·reader/등록 입력의 verified relocation과 현재 opener다. CB04/05의 결과 field/native asset bytes 보존과 Qt 원 배열 읽기는 그 기능의 대체가 아니다. 별도 상위 broker/일반 framework·새 파일형식은 추가하지 않는다.
