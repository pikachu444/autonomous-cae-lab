# PRO-FATIGUE-COMPLETION-20261015-01 — 작성·검사 인도

> 아래는 회수한 Pro 원본의 작성·Linux 실행 기록이다. Sol의 2026-10-16 현재 main 통합,
> 실제 Windows 계산·cold 재열기와 QWindows 화면 확인은 문서 끝의 후속 항목에 별도로 기록한다.

## 작성 범위

CMB total-strain/NONE, 같은 cycle의 σmax를 사용하는 단축 SWT, 최대 정상변형률 범위 면의 실제
CP-SWT engine을 작성했다. 기존 damage.rainflow/Simulation owner/JobManager/retention을 사용한다.
새 owner/store/server/schema framework/solver/provider가 아니다. 전용 Qt 편집기와 면→cycle→원행 결과
화면, 현재 초안 선택 반영과 기존 메뉴의 최소 연결 hunk를 작성했다. GUI 실행 검증은 아래처럼 미실행이다.

수학 helper만 반환한 것이 아니라 공개 tensor CSV를 실제 Data에서 가져와 저장하고, exact saved ref로
세 종류 Simulation을 계산·선택·저장한 뒤 원 입력과 작업 폴더를 없애고 별도 process에서 cold read한
runnable과 실제 기록을 함께 인도한다. 결과별 원행, closure/peak, root, 위치, partial/UNKNOWN과
반복 가정은 artifact에 보존한다. 구체적인 식과 한계는 MATHEMATICS.md, 사용은 USAGE_KO.md에 있다.

## 실제 검사

최종 관련 검사: **54 passed, 2 skipped**. skipped는 Qt 검사 **모듈 두 개**다. PySide6 미설치로 새 GUI
검사 3개와 기존 GUI 검사 2개의 본문은 실행되지 않았다. 이를 Windows 또는 offscreen PASS로 세지 않는다.

    python -m pytest -q tests/test_fatigue_strain_math.py tests/test_fatigue_strain_workflow.py tests/test_fatigue_workflow.py tests/test_fatigue_strain_editor.py tests/test_fatigue_editor.py

수학/입력 전용 47개, 새 owner 경계 2개, 기존 S–N 회귀 5개가 실제 통과했다. 사전 값과 허용치는
PREDECLARED_CHECKS.md에 테스트보다 먼저 기록했다. 알려진 Nf=10/1000/1000000의 NONE/SWT 역산에서
최대 Nf 상대오차는 1.2568198144435883e-11, 사전 허용치는 2e-9였다. Pa/MPa와 1/% 변환,
no-root/비수렴/압축 전용/범위 밖 UNKNOWN, 전단 2배 의미, 동시 tensor admission, 원행 loop membership,
서로 다른 면 선정 반례, 비례·비비례·회전·격자 개선, residual peak 대응을 포함한다.

실제 기존 owner 검사에는 원 saved ref 손상과 private payload 거절, 저장 최종 pointer 실패 주입,
이전 결과/현재 초안 보존과 명시 재저장, JobManager에서 완료 면 두 개 뒤 취소, CANCELLED 원 상태·완료 면
저장 및 새 owner 무계산 읽기가 있다. 면 처리 실패 주입은 FAILED를 유지하고 완료 면을 보존했다.

실제 FC06 최종 명령:

    python examples/impact/strain_fatigue_example.py --output /mnt/data/fatigue_work/evidence/fc06-release

| 계산 | 실제 유한 이력 D | 사전 기대 D | 실제 반복 블록 등가 수명 | 실제 면 수 |
|---|---:|---:|---:|---:|
| CMB/NONE | 0.001999999999974872 | 0.002 | 500.000000006282 blocks | 1 |
| 단축 SWT | 0.001999999999974872 | 0.002 | 500.000000006282 blocks | 1 |
| CP-SWT | 0.001999999999974872 | 0.002 | 500.000000006282 blocks | 133 |

세 비교의 상대 허용치는 실행 전 2e-9로 고정했다. 공개 0..2 s 이력의 실제 공급값을 사용했으며
각 표시 면에서 4개 half-cycle 기록을 보존했다. Data import 1 job과 fatigue 계산 3 job이었다.
FE/native/constitutive solver와 provider 호출은 코드 경로상 0이다. Data import를 FE 실행으로 세지 않았다.

원 CSV, 원 작업 폴더, 복사본의 live input/job 경로를 제거한 뒤 **별도 Python process**에서
retained source preview, 동일 결과 hash·면/cycle/원행 선택, invalid `1e` 초안 저장·실행차단,
stale current CAS 거절, 명시 repair/save와 원결과 불변성을 확인했다. cold의 새 job은 0이었다.
parent/child PID와 실제 assertion 결과는 verification/fc06-release/RUN_RESULT.json에 있다.
모든 실제 owner/자식 process 정리는 finally에서 수행했다.

## 실패 이력과 교정

원 공개 source와 최초 기록은 보존했다. 첫 새 수학 검사는 38 passed였다. GUI의 첫 정적 컴파일에서
new callback 들여쓰기 오류가 나왔고 교정했다. 첫 확대 검사에서는 51 passed/1 failed/2 skipped였다.
실패는 새 취소 검사에서 Workbench에 없는 `cancel`을 호출한 AttributeError였다. 실제 기존 API
`wb.manager.cancel`로 검사와 runnable의 timeout 경로를 교정했다. 다음 관련 검사는 53 passed/2 skipped,
residual σmax 비교의 절대 바닥값 제거 반례를 추가한 최종 검사는 54 passed/2 skipped였다.
첫 실패를 PASS로 소급하지 않았다. 원 실패 로그와 교정 설명은 verification에 포함한다.

GUI/core/runnable Python 구문 컴파일은 실제 수행했다. **Qt를 import하여 창을 실행한 검사는 아니다.**
정확 baseline 별도 사본에 patch 적용과 before/after 비교를 수행하며 그 결과는 PATCH_APPLY_CHECK.json에 있다.
ZIP 실재 크기/SHA256/CRC/멤버 명세는 인도 integrity 파일로 제공한다. 이는 수학 또는 Windows 검증과 다르다.

## 환경과 미실행

Linux 6.18.44 x86_64 / Python 3.13.5. numpy 2.3.5, matplotlib 3.10.8, jsonschema 4.26.0,
pytest 9.0.2, filelock 3.29.0이 기존 환경에 있었다. pytest/filelock은 프로젝트 pin 8.4.2/3.32.7과 다르다.
PySide6는 없었다. 새 package/설치/다운로드/유료 API/서버를 선행하지 않았다.

**NOT_RUN:** 실제 Windows pinned runtime/Qt 화면, 한글·포커스·좁은 창의 시각 검사, 실제 Windows
비동기 읽기·취소/복구, 원 native model의 완전한 total-strain tensor 공급 경로, FE/Impact solver 실행,
Astra 독립 수학·source 검토, root의 최신 main 통합·원격 게시. Linux 구문/owner 검사와 이 항목을 합치지 않는다.

기존 native catalog에 stress만 있고 total strain이 없다면 해당 SWT/CP-SWT 입력은 실행 차단/미정이다.
새 solver를 돌리거나 σ/E로 값을 만들어 완전한 native tensor 입력인 것처럼 표시하지 않았다.

## 완료와 남은 경계

선택한 CMB/NONE·단축 SWT·normal-strain CP-SWT의 코드, 전용 화면 작성, 합성 수학과 기존 owner 저장/cold
경로는 이 인도에 있다. **Windows GUI 수용과 독립 검토까지 끝난 C 전체 완료를 주장하지 않는다.**
SWT의 원 표본/half-branch association은 명시한 v1 확장이며 실재 재료 적용성은 별도로 검토해야 한다.

FS/shear 기반 수명, cyclic Ramberg–Osgood 근사, 비비례 추가경화와 반복 소성 state, cohesive fatigue 연계는
이 모델에서 구현하거나 검증했다고 주장하지 않는다. Impact A 일반 native 입력/실행과 B bulk/interface
손상은 별도 담당의 원잔여다. A/B, 전체 B2 또는 실재 재료 engineering qualification을 이 인도로 완료 처리하지 않는다.

소유와 patch 적용은 INTEGRATION.md 및 BASE_AND_FILES.json을 따른다. 공유 전체 파일은 반환하지 않으며
Data/Runner·Contact/S2/B13/C3B/finite-measure 병렬 변경을 되돌리지 않는다.

## Windows 통합 확인 — Sol, 2026-10-16

현재 `5109a9c`의 파일과 대조해 Pro 신규21경로를 원 해시로 추가하고,
`fatigue.py`의 세 호환 dispatch와 기존 편집기/결과창 연결을 최소 hunk로 적용했다.
root는 `simulation_document.py`의 지원 설명 한 줄만 별도로 반영했다.
기존 충격 결과 다시 읽기와 늦은 선택 보호는 그대로 유지한다.

원 수식·교정 범위·root 공차·UNKNOWN/실패 판정은 수정하지 않았다.
Windows Python3.13의 관련 core/owner/S–N 검사54개, QWindows6.9.1의 새·기존
GUI 검사7개가 통과했다. 원 공개 합성 예제로 Data1개와 피로 계산3개를 실행했고,
세 방법의 D≈0.002 및 반복 블록 수명≈500을 원 `2e-9` 상대 허용치로 확인했다.
원 입력/실행 폴더를 없앤 저장 사본은 별도 프로세스에서 같은 결과·선택으로 다시 읽었다.
이 과정의 FE/native solver 및 provider 호출은0이다.

실제 QWindows 창에서는 저장된 합성 결과를 기존 로컬 HTTP로 읽었다.
조건창1180×820/760×600, 결과창1180×870/760×680에서 한글과 선택·포커스,
부분 숫자 입력 취소, 면·사이클·원행 복원을 확인했다.
결과창에서 다른 면/원행을 **현재 초안에 반영 → 저장**한 뒤 HTTP 서비스를 종료하고
별도 Python 프로세스에서 그 선택과 동일한 원결과를 읽었다. 새 계산은0이었다.
Qt 입력 확인은 자동 Qt 이벤트이며 실제 사용자의 OS 키보드 조작 수용과 구분한다.

Sol이 교정한 것은 Qt tuple↔QVariantList 차이로 정상 방법이 미완성으로 표시되던 선택기,
입력표를 가리던 긴 검토 상태, 결과창의 과도한 최소 높이와 선택 위치 복구,
한국어 화면명과 Simulation의 단일 피로 작업 진입이다. 수학 core는 Pro 원문이다.
실제 before/after 렌더와 재현 driver는 `_workspace/delivery-fatigue-c/`에 있다.
`fc06-windows-01/RUN_RESULT.json`, `qt-tests-final.xml`,
`windows-save-03/REPORT.json`과 각 `*-process-*/native-check.json`이 실행 원본이다.
모든 소유 process/자식은 종료했고 `cleanup=job_empty`를 확인했다.

두 GUI cold 검사는 서비스가 같은 작업공간을 소유한 상태에서 두 번째 controller를 열어
검사 driver가 실패했다. 제품 저장 실패로 바꾸지 않고 원 로그를 보존했다.
서비스를 종료한 후 cold를 여는 `windows-save-03`에서 통과했다.

실측 교정 계수와 실제 native 모델의 완전한 total-strain 공급, FE/충격 솔버 실행,
전단 지배 재료의 적합성·FS·반복 소성·계면 피로 자격은 이번 확인에 포함되지 않는다.
독립 검토와 원격 게시는 root가 해당 결과를 별도로 기록한다.
