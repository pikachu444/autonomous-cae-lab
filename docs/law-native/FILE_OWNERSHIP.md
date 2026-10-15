# File ownership / integration boundary

PRO-LAW-NATIVE-20261015-01. 이 인도는 사용자 첨부 3ba7c97+pin3e48의 실제 snapshot에 대한 것이다. 공개 main의 이후 b2e359d나 Numerical/Expert/R2/Impact/B13/PDE/Portable/Post 병렬 WIP를 읽고 통합했다고 주장하지 않는다.

## 전용 파일

| 경로 | 작성 책임 / 실제 내용 |
|---|---|
| plugins/material_point/drucker_prager.py, single_branch_native.py, law_native*.py | Pro 전용 DP/상태/measure/independent probe/history·law binding |
| caelab/adapters/law_native*.py, caelab/law_native_fe.py | Pro point/기존 FELUPE spatial worker/실제 runtime recorder |
| caelab/material_fe_transfer.py, material_law_validation.py, law_native_inspection.py | Pro 저장 revision·mapping/typed command·기존 fit/reader/inspector adapter |
| apps/desktop_pre/law_native_material.py | Pro 기존 native owner transaction/geometry mesh identity/admission/assignment/freezer |
| apps/research/law_native_material_window.py, law_native_transfer_dialog.py | Pro가 계약 실행 가능한 전용 Qt 연결 작성; Sol이 현재 제품 GUI에 정합·실제 사용성 확인 |
| tests/law_native/, examples/material-tests/law-native/, tools/law_native/, docs/law-native/ | 전용 관련 검사·독립 기준·작은 공개 입력·owned Windows/native 실행기·사용법 |

새 전역 store/owner/registry/schema compiler/optimizer/FE solver/framework가 없다. 기존 service/client/native owner/MaterialDocuments/SimulationDocuments/JobManager/Data/Numerical CAS를 재사용한다. fixed Python law source snapshot은 기존 immutable revision의 asset이다.

## 공통 최소 hunk — root 소유

아래 기존 파일은 root-integration.patch만 제공한다. 전용 source 폴더에 과거 shared 전체파일 overlay를 넣지 않는다. 현재 main에서 hunk의 의미를 기존 병렬 수정과 수동 정합하고 현재 suite의 관련 범위만 검사한다.

- `apps/desktop_pre/bridge.py`
- `apps/desktop_pre/fem_edit.py`
- `apps/desktop_pre/freeze_analysis.py`
- `apps/desktop_pre/freeze_contact.py`
- `apps/research/constitutive_inspection_window.py`
- `apps/research/material_window.py`
- `apps/research/simulation_window.py`
- `caelab/adapters/native_doctor.py`
- `caelab/backends.py`
- `caelab/constitutive_inspection.py`
- `caelab/material_control.py`
- `caelab/material_document.py`
- `caelab/native_commands.py`
- `caelab/numerical_document.py`
- `caelab/research_execution.py`
- `caelab/simulation_document.py`
- `caelab/workbench.py`


Workbench/client에는 새 보안권한/임의 source endpoint를 만들지 않는다. 공통 hunk는 새 backend/typed command/기존 GUI 분기/strict reader projection 연결 및 옛 CalculiX fallback 차단에 한정한다. Material control의 private validated context 확장은 기존 default 호출 동작을 유지한다. 원 arbitrary MFront build 승인/Linux guard, 원 Data fit schema/CAS, 원 result admission은 교체하지 않는다.

## 적용

`dedicated.patch`는 새 전용 파일만, `root-integration.patch`는 위 17개 기존 파일의 최소 수정만 포함한다. `dedicated/`는 새 파일의 실제 bytes이며 두 patch 적용 결과와 같은 내용이다. CHANGE_LIST.json의 before/after hash와 파일 목록을 확인한다. 전체 source.zip overlay, 전체파일 삭제, CURRENT_STATE/HANDOFF/Space 수정은 없다.

첨부 정확한 기준에서 다음 순서의 적용/bytes 동등성은 delivery evidence/patch-apply.json으로 확인한다. 다른 main에 자동 적용 성공을 주장하지 않는다.

```
git apply --check dedicated.patch
git apply dedicated.patch
git apply --check root-integration.patch
git apply root-integration.patch
```

실제 Windows 연결·배포는 root, 전용 GUI 제품 정합은 Sol, 독립 수학·코드 검토는 Astra 담당이다. 이 ZIP에 있는 Linux pytest/controlled fixture만으로 이들의 실제 검토/실행을 대신하지 않는다. 옛 전체파일로 다른 팀 변경을 덮지 않는다.
