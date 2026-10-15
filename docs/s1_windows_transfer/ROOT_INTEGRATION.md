# Root 통합 — 최소 패치, 원 기준 보호

기준 Git `67a861e17415f19cc42838f82685f4f48c041ef5`, fixture pin `3e48bf6138f495299f45b1af254bfb4aaff307b8`.
첨부 548개 원 파일의 SHA256 및 Git blob을 모두 확인했다. source ZIP은 3,007,767B,
SHA256 `932f0661c25f2a271dc2a6d8424a9b416beed147f7c3da3f2b15c9ea855a8803`다.
원 첨부와 원 failure/물리 기준을 변경하지 않는다. 현재 main b2e359d의 WIP를 읽은 것으로
가정하거나 통째로 덮어쓰지 않는다. 실제 GitHub 게시/현재 main 병합은 수행하지 않았다.

## 인도 파일과 순서

`product.patch`는 새 전용 모듈·관련 시험·공개 예제·문서와 Pro 소유
`caelab/evaluation_definition.py`, `caelab/transfer_inspection.py`의 **최소 diff**를 포함한다.
`dedicated/`에는 새 파일 원문만 넣었다. 기존 shared 파일의 완성본 덮어쓰기 사본은 없다.

`integration.patch`는 root가 소유하는 기존 파일 11개의 최소 증분이다. 적용 경계는
아래 표와 change-manifest.json에 있다. 먼저 product.patch, 그 다음 integration.patch다.
원 기준에서 두 패치를 적용하는 검사는 `verify_and_apply.py`를 사용한다.

```powershell
# 깨끗한 동일 기준 복사본에서만. 현재 병렬 main에 직접 실행하지 않는다.
python <인도폴더>\verify_and_apply.py --root <깨끗한-67a861e-폴더>
python <인도폴더>\verify_and_apply.py --root <깨끗한-67a861e-폴더> --apply
```

기본은 모든 입력 hash/새 경로 충돌/패치 적용 가능성 검사만 한다. --apply 시에도 모든
검사를 선행하고 적용 뒤 모든 목표 hash와 548개 기준 파일 존재를 확인한다. original hash가
다르면 강제로 덮어쓰지 않는다. reset/clean/checkout/rm/whole-file-copy를 하지 않는다.
한 패치 적용 후 두 번째에서 예상 밖 실패가 발생하면 원인을 반환하며 자동 reset하지 않는다.
실제 깨끗한 적용 검사/동일 소스 hash/구문 검사/새 S1 재검사 기록은 ZIP의 evidence에 있다.

현재 main에서는 root가 이 diff의 각 hunk를 기존 병렬 변경에 병합한다. 원 SHA 기준 hash가
다르므로 위 strict script는 main 통합 도구가 아니다. 새 파일 경로도 기존 작업에 이미 있으면
비교 후 통합한다. 약형식/해석 선택기/후보/Study/전달 창의 다른 팀 변경을 되돌리면 안 된다.

| 기존 공통 파일 | 최소 변경 목적 |
|---|---|
| `caelab/backends.py` | 새 lazy backend 3개 등록 |
| `caelab/adapters/native_doctor.py` | 기존 Windows FEniCSx guard 유지, 새 service-Python capability만 별도 discovery |
| `caelab/dimensioned_models.py` | 새 backend를 기존 AST/binding API에 위임 |
| `caelab/pde_document.py` | 새 capability의 독립 PDE owner 설명 |
| `caelab/simulation_document.py` | 기존 Simulation catalog/declaration에 2개 adapter 연결 |
| `caelab/workbench_cli.py` | 동일 Client의 inspect/stages/stage/transfer 조회 |
| `apps/research/pde_window.py` | 기존 식/물리/clock editor와 SI field/Post selection 확장 |
| `apps/research/simulation_window.py` | 모델 선택·경계 온도 gradient·absolute/difference mode |
| `apps/research/evaluation_window.py` | 기존 port picker의 새 mapping 정책/명시 dialog |
| `apps/research/transfer_inspection_window.py` | 기존 exact view 유지, 별도 P1 source/receiver view 연결 |
| `pyproject.toml` | 선택적 spatial dependency pins 추가 |

Workbench/routes/client/JobManager/owner registry/schema/store/Numerical/Expert/Data/Portable/
B13/동해석R2/Post native 파일은 새 전체 파일로 교체하지 않는다. 이 기능은 기존
`evaluation_transfer` HTTP/client/Workbench 경로가 이미 있으므로 해당 공통 파일 변경은 필요 없다.

## MCP: 첨부 closure 밖의 별도 최소 패치

`openscience/workbench_mcp.py`는 원 첨부 548개에 없다. 공개 GitHub connector로 동일
기준 commit의 해당 파일/필요 문맥을 읽었고, 반환된 원 Git blob은
`1a633c6e2dcae649b0b77d1a582260ecf3bdc26a`다. default branch의 파일을 대신 쓰지 않았다.

`mcp-integration.patch`는 기존 client() 다음에 아래 등록만 추가한다.

```python
from caelab.temperature_transfer_mcp import register_transfer_tool
register_transfer_tool(mcp, client)
```

원 MCP 서버/Client factory/기존 도구는 그대로다. 새 서버를 만들지 않는다.
원 full file bytes는 컨테이너로 받지 못했다. 따라서 **이 MCP 별도 패치의 full-file clean
apply 및 SDK/stdio 실행은 NOT_RUN**이다. 일부 source context를 가짜 전체 파일로 만들어
PASS를 얻지 않았다. product.patch/integration.patch의 실제 548파일 적용 검증과 구분한다.

기존 전체 저장소에서 root는 해당 원 파일의 Git blob 및 수정 문맥을 확인하고 병합한다.

```powershell
git hash-object openscience/workbench_mcp.py
git apply --check <인도폴더>\mcp-integration.patch
# 원 파일에 병렬 변경이 있다면 직접 hunk 병합. 위 hash는 기준 blob과 비교한다.
```

`caelab.temperature_transfer_mcp.register_transfer_tool` 자체와 등록된 함수의 실제 HTTP
호출은 명시적 decorator 시험 대역으로 확인했다. MCP SDK로 같은 과정이 동작했다고
주장하지 않는다. `evidence/supplemental-mcp.json`에 원 기준/상태를 보존한다.

## 유지한 실행 경계

`evaluation_definition.execute`의 기존 stage order/attempt ID/lag/Picard/취소/prefix reuse를
사용한다. `DefinitionFactory`를 대체하지 않는다. successful exact prefix reuse와 definition/
values drift 거절, partial-loop reuse 금지를 유지한다. mapping 뒤 추가 취소 확인은 후속
receiver 제출을 막는 목적이다. retained writer/reader나 source capture 저장소를 새로 만들지 않는다.

새 actual solver test는 설치된 고정 버전을 요구하며 미설치 때 명시 NOT_RUN skip한다.
설치된 다른 버전은 PASS나 skip으로 넘기지 않고 FAIL한다. 원 residual/free-expansion/
temperature bounds를 고치지 않았다. 원 Post 시험 대역 2건 실패는 baseline에서 재현·보존했다.

## 역할과 다음 시작 의존

이번 core 작성물과 관련 GUI 증분은 S1 통합 후보 소스다. Sol GUI 통합/실제 렌더 및
Astra 독립 검토/Windows 실행을 수행했다고 표시하지 않는다. Root가 공통 병합 및 Windows
원실행과 재열기 결과를 확인한다. 현재 본문과 ZIP은 전체 S1 수용 완료 기록이 아니다.

S2 담당은 이 backend/field/clock/binding/retained API에서 바로 이어갈 수 있다. 기존 Picard를
미구현으로 다시 만들지 않고 기존 공유 binding/DefinitionFactory/optimizer를 사용한다.
S2의 실제 공유 변수 후보/수렴·실패·취소/새 owner와 실제 adjoint/Taylor 검사는 남아 있다.
