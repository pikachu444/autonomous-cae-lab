# 접촉·주기 구속·합력/모멘트 — RECOVER1 인도

요청: PRO-CONTACT-USER-MODEL-20261015-01-RECOVER1

**2026-10-15 Windows 통합 상태:** 아래는 Pro가 작성한 원 범위와 실행 경계다.
통합 후 Sol이 단계별 출력 등록/읽기를 교정했고 실제 CalculiX의
비활성→활성→비활성 계산, 같은 원출력의 저장·새 프로세스 읽기와 Astra 검토를 마쳤다.
활성 단계의 실제 0과 비활성 단계의 미출력을 구별한다. 새 단계 조건의 FreeCAD
저장, 전체 ParaView 창 왕복, 주기 구속의 실제 계산과 공학적 적합성은 미확인이다.
기본 접촉 기능은 기존 FreeCAD FEM·CalculiX를 재사용하며 새 접촉 솔버를 만들지 않는다.

## 이번 작성물의 위치

이 인도는 원 작성 소스를 회수한 것이 아니라, 첨부한 공개 기준
`583ad1ae473787ea580fdafcf89b01a5a6ec1e5e`의 실제 536파일에서 **새로 작성한 구현**이다.
재개 시 작업 폴더에는 원 첨부 네 파일만 있었고, 이전 작성 코드와 109개 검사 로그는 없었다.
따라서 이전 109개는 재검증하거나 이번 실적으로 합산하지 않는다.

기존 contact/FEM owner, 단계 compiler, CalculiX adapter, DAT/FRD reader,
Post measurement owner와 Numerical 전달 계약을 확장한다. 새 solver, 메시 엔진,
JobManager, 결과 저장소, FE framework를 만들지 않았다. 기존 GUI와 native 실행 경로를
사용하며 AI/MCP/WSL/유료 API를 일반 실행 조건에 추가하지 않는다.

이번 범위는 다음 세 묶음이다. 입력 생성·저장·reader·GUI 연결 코드는 포함하지만,
이 컨테이너에서는 실제 FreeCAD/CalculiX/ParaView/Qt/Windows 수용을 실행하지 않았다.
수학적 식과 입력 카드의 확인을 실제 solver 해의 수용으로 바꾸지 않는다.

## 1. 단계별 접촉 활성 제어

기존 FEM 편집기의 **해석 단계**에서 **단계별 접촉쌍 활성 상태를 명시**를 켠다.
모든 단계에 모든 실행 대상 접촉쌍의 상태를 명시한다. 예를 들어 세 정적 단계에
`비활성 → 활성 → 비활성`을 지정한다. 첫 단계에서 REMOVE, 둘째에서 ADD,
셋째에서 REMOVE를 기존 단계/하중 카드 사이에 생성한다. 기존 하중·변위 곡선과
접촉쌍 면 대응은 변경하지 않는다. 상태 지정을 사용하지 않는 기존 입력은 그대로다.

실행 가능한 입력 범위는 기존 선형 pressure-overclosure surface-to-surface 접촉,
정적 단계와 선형 탄성 재료다. 기존 frictionless/Coulomb 선택과 geometry 설정을
자동 변경하지 않는다. 새 단계 상태와 동해석·restart·소성 재료의 조합은 차단한다.
처음 비활성이던 쌍의 활성화는 표현하지만, 이미 활성 단계를 거친 뒤 제거한 쌍을
다시 활성화하는 이력은 `CONTACT_REACTIVATION_UNKNOWN`으로 차단한다.

**기존 `*TIE` 해제는 구현하지 않았다.** `*TIE`의 MPC를 접촉쌍 제거로 바꾸지 않는다.
묶음 해제를 입력한 초안은 저장할 수 있지만 freeze/run은 `TIE_RELEASE_UNSUPPORTED`로
거절한다. 일반 접촉에는 비활성을 사용하며 묶음 해제로 해석하지 않는다.

적용 시 편집을 시작한 source/revision을 확인하고 기존 document transaction으로
저장한다. 응답을 잃으면 같은 요청 재시도를 사용한다. 같은 명령을 두 번 적용하지
않고, 사이에 면·쌍·입력이 바뀌었다면 stale 오류로 다시 읽기를 요구한다.
실패·미완성 초안을 몰래 정상값으로 고치거나 기존 실행 결과를 덮지 않는다.
상태 지정을 끌 때는 전체 기본 활성으로 돌아가는 의미를 확인한다.

Post에는 **입력상 쌍 활성 상태**와 실제 solver의 접촉 상태를 분리한다.
활성 입력이라는 이유만으로 접촉 중이라고 표시하지 않으며 기존 `active_state=UNKNOWN`을
유지한다. 비활성 시 DAT가 없는 경우도 0 힘을 만들어 넣지 않는다.

## 2. 주기 경계의 절점 구속

기존 FEM 편집기의 **주기 구속** 탭을 사용한다. 3D에서 여러 면을 선택하여
**선택 면 영역 저장**으로 기존 FEM 면 영역을 만든 뒤 A와 B를 지정한다.
이 면 영역 저장은 별도 명시적 document 편집이다. 이후 구속 폼을 취소해도 이미
저장한 면 영역까지 자동 삭제하지 않는다. 필요하면 기존 Undo를 사용한다.

병진 주기는 A→B 이동량을 mm로 입력한다. 회전 주기는 문서 전체 좌표의 축 기준점
[mm], 축 방향, 각도 [°]를 입력한다. 대응 허용오차 [mm]는 사용자가 지정한다.
입력한 변환 후 A의 모든 면 절점이 B의 절점과 하나씩 대응해야 한다.
C3D10의 중간 절점도 포함하며 빠진 절점, 잘못된 축, 중복·모호한 대응을 거절한다.
가까운 절점을 임의 채택하거나 보간하여 누락을 숨기지 않는다.

생성식은 병진에서 `u_B = u_A`, 회전에서 `u_B = R u_A`이다.
이는 **고체 병진 DOF 1·2·3의 회전 좌표 대응**이지 DOF 4·5·6을 갖는 회전 요소가 아니다.
B측 DOF를 native `*EQUATION`의 종속항으로 사용한다. B측 고정/지정 변위와의 중복,
자기 의존, 순환·연쇄, 불완전 면 대응은 실행 전에 차단한다.
균질한 주기 변위만 다루며 비균질 macrostrain/변위 jump를 0으로 대체하지 않는다.

이번 입력 범위는 기존 C3D10 고체의 정적·소변형·선형 탄성이다.
접촉/묶음과 주기 구속을 같은 모델에서 결합하는 경로, 회전축 공유 절점,
비대응 메시 보간, NLGEOM/소성/동해석/restart 조합은 미완료이며 차단한다.
구속은 contact law enum이 아니라 기존 FEM owner의 별도 구속 기록이다.

저장·다시 읽기·삭제·면 강조·Undo/Redo와 요청 재시도는 기존 owner/transaction을 사용한다.
면이나 메시가 바뀌면 기존 명시적 면 재지정을 거친 뒤 새 입력을 만든다.
기존 실행 결과나 이전 frozen mesh를 자동 수정하지 않는다.
초안에 숫자 입력이 미완성이면 저장은 가능하지만 실행 전 검증에서 거절한다.

## 3. 접촉쌍 합력·기준점 모멘트와 Numerical

기존 Post의 **접촉면·합력·모멘트** 창에서 원 결과의 접촉쌍·DAT 물리량
(CF/CFN/CFS)·성분·저장 증분을 선택한다.
**기준점·좌표계를 지정한 합력 / 모멘트**를 켜고 응답 종류, 좌표계 이름,
기준점 [mm]과 세 로컬 축을 입력한다. 세 축은 문서 전체 좌표로 표현한
오른손 직교 단위 벡터다. 자동 직교화/정규화로 입력 의미를 바꾸지 않는다.

DAT의 A/slave 면 합력 F와 문서 원점 모멘트 M을 사용한다.
기준점 r과 로컬 축을 행으로 갖는 Q에 대해
`F_local = Q F`, `M_local = Q (M - r × F)`를 계산한다.
모멘트 단위는 **N*mm**이며 N*m로 조용히 바꾸지 않는다.
B면이나 양면 합계를 A의 부호 반전/중복 합산으로 추정하지 않는다.
공유 절점 CONTACT FRD 투영장을 pair별 traction/status로 재라벨링하지 않는다.

**선택 조회**, **현재 면과 증분 저장**, **합력 / 모멘트 측정 저장**을 사용한다.
선택한 저장 증분만 포함하려면 해당 체크박스를 켠다. 선택한 frame index,
원 pair/quantity, 성분, 기준점, 좌표계, 측도, 단위와 시간축을 측정에 보존한다.
보간·행 순서 변경·누락값 0 채우기는 하지 않는다.
원 자료에 선택 성분이 없으면 None/미제공 이유를 유지하며 VTK 표에서는 NaN으로 저장한다.
아예 다른 측도나 잘못된 source association은 실행/측정 작성 오류로 남긴다.

**Numerical로 보내기…**는 기존 review/append 경로를 사용한다.
정적 하중 계수와 물리 시간을 서로 바꾸지 않고 같은 측도·단위·좌표계·원 증분을
검증한다. 검토/취소는 Numerical 자료를 수정하지 않는다. 이미 저장한 측정과
원 결과 핀을 바탕으로 다시 열며 원 파일이 바뀌면 새 자료로 몰래 채택하지 않는다.

## 실행 경계와 유지되는 소유권

새 단계 상태 또는 주기 구속이 있는 입력만 기존 실행 제어로 `ccx -v`를 확인하고,
정확한 2.22 버전 표시가 없으면 solver 본 실행 전에 차단한다. 실행 파일명만으로
버전을 인정하지 않는다. probe는 기존 owned process cleanup을 사용한다.
기존 입력/attempt/실패 로그를 보존하고 별도 runner를 만들지 않는다.
버전 일치는 물리 수용의 대체 근거가 아니다. 실제 native 수용 상태는 UNKNOWN/NOT_RUN이다.

현재 지원되는 조합의 입력 생성 경로와 미확인 조합의 run-block을 분리한다.
이번 작성 때문에 이전 TIE/penalty/하중/결과의 기존 지원을 소급하여 실패로 바꾸지 않는다.
새 기능의 범위를 B1.5/B1.6 전체 완료라고 보고하지 않는다.

## 설치·통합

ZIP의 `source/`는 **전용 소스·테스트·예제·문서만** 담는다.
공통 파일의 전체 사본은 넣지 않았다. `product.patch`와 `root-integration.patch`는
제공된 정확한 baseline을 기준으로 한 unified diff다. 저장소 루트에서:

```text
git apply --check <인도폴더>/product.patch <인도폴더>/root-integration.patch
git apply <인도폴더>/product.patch <인도폴더>/root-integration.patch
```

두 패치를 적용한 fresh 기준 사본에서 관련 검사를 다시 실행했다.
현재 main/병렬 WIP에는 reset/전체 source overlay를 하지 말고 root가 최소 hunk를 통합한다.
새 SDK/상태 변경, Law 두 창, B13/C3A/B13Post의 최신 전체 트리 적용은 이번 검사가 아니다.
참조 보호 84파일과 이번 변경 경로의 교집합은 없으며 CURRENT_STATE/SPEC도 변경하지 않았다.
공통 경계는 FEM dispatch·panel refresh/오류 표식·freeze hook·solid route 선택·registry·
Post 측정 설명 여섯 파일의 최소 변경이다. 다른 owner의 Law export guard를 유지한다.

upstream pin `3e48bf6138f495299f45b1af254bfb4aaff307b8`은 원 첨부의 지정값이다.
해당 submodule 전체는 원 536파일 ZIP에 없었으며 이번에 변경하거나 실제 실행했다고
주장하지 않는다. 실제 작성 기준은 검증한 원 첨부 파일들이다.

## 검사 재현과 증거

필요 패키지가 설치된 기존 개발환경에서 PowerShell은 `$env:PYTHONPATH=".;tests"`,
POSIX는 `PYTHONPATH=.:tests`를 사용한다. 새 유료 의존은 없다.

```text
python -m pytest -q tests/test_contact_recover1.py tests/test_contact_recover1_qt.py tests/test_contact_steps.py tests/test_contact_execution.py
python -m examples.contact.recover1_periodic_cube <존재하지 않는 출력폴더>
```

예제는 작은 독립 C3D10 주기 입력의 `.inp`와 모델 JSON만 생성한다.
가짜 FCStd/owner 영수증/solver 해를 만들지 않으며 실제 사용자 CAD 입력을 대신하지 않는다.
관찰한 89 passed / 1 skipped는 관련 portable 검사 결과다.
실제 VTK 표 저장/재열기, 기존 Numerical 검증 계약, 실제 Python 자식 프로세스의
성공·실패·timeout 회수는 포함한다. FreeCAD/ParaView/solver 호출은 명시적 대역이다.
PySide6가 없어 Qt 모듈은 skip했다. 원래 보고된 109개는 NOT_VERIFIABLE이다.

이전 실패 로그도 보존한다. 첫 기존 검사 수집은 원 ZIP에서 빠진 Post 테스트 보조
모듈 때문에 중단됐다. 새 검사 작성 중 잘못된 예제 인수와 검사 설정을 고친 과정도
원 로그로 남는다. 기존 `test_contact_native_export.py`의 3개 실패는 원 baseline에서도
같으며, Law guard가 요구하는 owner.read_metadata가 오래된 대역에 없기 때문이다.
그 원 검사를 통과한 것으로 바꾸지 않았다. 별도 새 검사에서는 실제 owner 인터페이스를
제공하는 대역으로 기존 exporter 계약을 확인하며 Law guard 자체는 끄지 않았다.

실제 Windows 수용은 별도다. 사용자 multi-face 모델의 입력 생성→native 실행→
원 attempt Post 재열기, periodic 실제 해의 각 DOF/식 검증, FreeCAD 저장/새 세션,
Qt 편집/Undo/응답 유실 UX, ParaView 실제 화면과 전체 Numerical GUI는 NOT_RUN이다.
실행 도구가 없다는 이유로 통과/0 결과를 만들지 않았다.

## 공식 근거와 남은 원 요구

참조한 CalculiX 소스는 2.22 pin
`cff1bb12ec7d24ad9048a1f54ae243a18d1a0b54`의 `src/modelchanges.f`,
`src/equations.f`, `src/printoutcontact.f`다. 저장소의 GPLv2 헤더와 실제 parser/
합력·원점 모멘트 계산을 확인했다. `*MODEL CHANGE`를 *TIE 해제로 사용하지 않는 이유와
A/slave DAT 모멘트 변환의 근거다. solver 소스/바이너리는 인도 ZIP에 재배포하지 않는다.

https://github.com/Dhondtguido/CalculiX/blob/cff1bb12ec7d24ad9048a1f54ae243a18d1a0b54/src/modelchanges.f
https://github.com/Dhondtguido/CalculiX/blob/cff1bb12ec7d24ad9048a1f54ae243a18d1a0b54/src/equations.f
https://github.com/Dhondtguido/CalculiX/blob/cff1bb12ec7d24ad9048a1f54ae243a18d1a0b54/src/printoutcontact.f

hard/no-penetration, implicit cohesive와 mixed-mode/압축 재접촉, small/large sliding
확장, 실제 *TIE 해제, 곡면·경계·연쇄 Tie Adjust, 사용자 Code_Aster S2,
pair별 독립 pressure/gap/slip/status reader, 확대된 비선형 조합은 **미완료로 남는다**.
고정 benchmark, penalty 상향, 명칭 변경, explicit Impact 또는 미지원 표로 닫지 않는다.
