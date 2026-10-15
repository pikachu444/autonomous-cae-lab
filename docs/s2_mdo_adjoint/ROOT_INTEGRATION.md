# Root 통합과 소유 경계

아래는 Pro가 반환 당시 작성한 통합 인계다. 현재 저장소에는 변경을 통합했으며 이후의
Windows 실행·표시 확인은 [Windows 기록](WINDOWS_ACCEPTANCE_KO.md), 현재 잔여는
[CURRENT_STATE](../../CURRENT_STATE.md)를 따른다.

정확 기준은 첨부 source.zip509파일(5ee81c544093b6feb78fc874fd09be380d47f223)이다.
Law/Post C1/B13/Portable 미게시 WIP는 packet에 없으며 추정해 추가하지 않았다. 원 CURRENT_STATE나
다른 팀 문서를 전체 교체하지 않았다. remote main을 변경·게시하지 않았다.

적용 순서: **product.patch → integration.patch → gui.patch**.

product: 새 공유 binding/선형 contract/actualadjoint worker+retention/SciPySLSQP 소비 및 기존 Pro 소유
Evaluation/numerical/S1 worker/모델/transfer reader의 최소 확장, 실제 검사·공개 예제·문서.
integration: Workbench 입력/사전 admission/방법별 예산 옵션, assist schema의 method/실제scalar reduction,
research_workflows의 기존 원 후보/adjoint/전달 읽기, workbench_cli의 같은 reader 선택. 이 **4개 공통파일과 EvaluationDocuments.inspect의 1개 owner hunk**는
실제 diff hunk만 제공한다. 전체 대체 사본은 적용 자료에 넣지 않는다.
gui: 기존 Qt Evaluation/RequestPlan/Candidate/TransferInspection 최소수정과 전용 공유입력/gradient widget.
실제 Qt 실행/Windows사용성은 NOT_RUN이며 Sol 연결·실창 검토용으로 분리했다. Sol 작성/검토를 사칭하지 않는다.

인도 루트 `CHANGE_MANIFEST.json`에 각 파일의 소유 group, base/result SHA, 새파일/수정 여부가 있다.
`verify_and_apply.py --source-zip 원source.zip --target 새빈경로`는 원509파일 bytes/SHA/Git blob을 먼저
확인한 뒤 3patch를 실제 git apply --check/apply하고 변경 후 모든 파일을 검사한다. 변경된 main에 강제
덮어쓰는 도구가 아니다. 현재 main은 root가 기존 병렬변경을 보존하며 hunk별로 병합한다. patch충돌을
강제처리하거나 지원파일 원문을 통째로 교체하지 않는다. 현재main에 직접 적용 완료했다고 주장하지 않는다.

새 명령 시스템/owner/store/scheduler/backend framework를 추가하지 않았다. 새로운 registry backend도
필요하지 않다. 원 scikit-fem thermal capability의 명시 derivative method와 기존 optimize 방법을 확장했다.
MCP는 원 Numerical/evaluation commands와 reader에 전달되는 payload의 확장이다. 첨부에 없는 MCP
서버 전체파일을 만들어 교체하지 않았다. 실제 runtime등록/stdio검사는 NOT_RUN이다.

상태 반영 제안: S2 공유 fan-out/actualnonlinearDE/선형adjoint+SciPyjac/Core cold는 구현·Linux증거 인도.
Qt/Windowsnative/독립검토와 넓은 nonlinear/shape/transient/coupled gradient는 미완료. 전체B6완료아님.
root는 실제 적용/Windows·Sol/Astra 검토 후 CURRENT_STATE의 해당 인도에만 반영한다.
