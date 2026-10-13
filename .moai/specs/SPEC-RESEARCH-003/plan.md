# 구현 인계와 진행 순서

Pro가 다음 사용자 작업 묶음을 작성하고, Codex가 Windows/WSL 연결과 통합을 맡는다.
Astra는 실제 선택·계산 의미와 화면을 독립 검토한다. D6 인도가 끝난 실제 통합 버전을
다음 요청의 기준으로 제공한다. 실제 배정과 진행은 CURRENT_STATE에서 관리한다.

## 재사용할 곳

| 작업 | 기존 구현 | 추가 연결 |
|---|---|---|
| 구성식 | `apps/research/native_material_window.py`, `caelab/material_document.py`, 기존 MFront/FELUPE adapters와 reference | 같은 Material의 증분별 응력·상태·잔차·접선 조사, 독립 perturbation, 명시 법칙 등록/빌드 |
| PDE | `apps/research/pde_window.py`, `caelab/pde_document.py`, `plugins/pde_nonlinear/reference.py` 등 등록 domain | 선택 field/식/BC/공간의 편집, 오류 위치, 실제 norm 비교, 일반식/ODE capability |
| 연성 | `apps/research/evaluation_window.py`, `caelab/evaluation_definition.py`, `plugins/thermoelastic/reference.py` | 선택 공급 장·수신 값 대조, 단위/mesh/time/mask, 반복 잔차와 실패·재사용 경로 |
| 도구 연결 | `apps/research/desktop.py`, 기존 client/desktop_links/JobManager | 선택 문서와 저장한 결과의 정확한 열기, Post/Runner/Numerical 왕복 |

먼저 기존 지원 모델의 사용자 작업을 연결하고, 법칙·일반식·전달 capability의 실제
누락을 같은 작업표에 구현/미구현으로 구분한다. 지원되지 않는 요구를 삭제하거나
입력칸만 추가해 완료로 표시하지 않는다. 다음 순서는 인터페이스 의존 관계이며,
그림이나 입력 폼 하나만 인도하고 전체 과제를 끝내는 순서가 아니다.

1. 현재 지원한 law/PDE/Evaluation의 같은 문서·결과를 읽어 필요한 실제 값을
   기존 reader에서 확보한다. 없는 state나 tangent pair는 만들지 않는다.
2. 증분 선택, 식/영역 편집, 실제 전달값 대조와 잔차를 도구의 중심 작업으로 연결한다.
   원본 열기·명시 실행·실패 복구·저장·재열기를 함께 작성한다.
3. 일반 law 등록/빌드, dimensioned weak form/ODE, 다른 mesh/단위 mapping은
   기존 기능에 덮어씌우지 않고 실제 domain/adapter capability를 추가한다.
   실행 환경 또는 독립 수치 기준이 부족한 항목은 구현 위치·남은 조건을 명시한다.
4. 관련 작은 실행과 결과 선택을 확인한 뒤 코드·사용 예제·지원 범위를 함께 인도한다.

## 기존 실행 환경

Windows Qt 실행 환경과 Ubuntu WSL 계산 환경이 모두 존재한다. WSL system Python에는
FEniCSx가 있고 기존 SIF에는 TFEL 5.0.0/MGIS 3.0이 있다. 이는 설치/버전 확인이며
이번 새 기능의 실행 통과는 아니다. 기존 `scripts/cae-research-local.ps1 -Execution WSL`
및 `scripts/local.ps1`의 실행 환경을 먼저 재사용한다. Windows Qt는 해당 서비스에
연결하되 같은 store/문서와 Windows↔WSL 파일 경로가 유지되는지 확인한다.
이미 설치한 환경의 실제 경로는 인계 때 제공하며 새 설치나 유료 서비스는 전제하지 않는다.

기술 확인은 새 지원 기능의 결정을 내리는 데 필요한 범위로 제한한다. 예전 전체
벤치마크를 다시 통과하는 일이 이 사용자 작업 묶음의 선행조건은 아니다.
