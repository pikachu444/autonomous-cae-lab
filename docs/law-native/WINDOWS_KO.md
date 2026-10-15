# Windows 실행·설치·실제 인수 경로

## 상태

현재 작성/검사는 Linux Python3.13.5에서 이루어졌다. Windows, FreeCAD, PySide6, FELUPE 공간 실행은 NOT_RUN이다. FELUPE 설치 DNS 실패 원로그는 인도 ZIP의 `evidence/install-felupe.log`에 있다. 설치를 시도했다는 사실은 FE 지원 인증이 아니다. 공식 wheel 직접 다운로드도 실패해 wheel을 번들하지 않았다.

이번 Windows 경로는 기존 Python FELUPE 고정 dependency를 사용하는 별도 capability다. MFront의 Linux guard를 제거하지 않는다. `/opt/activate.sh`, Singularity, WSL, 새 compiler나 DLL 추정, 유료 API/구독을 요구하지 않는다. 임의 사용자 MFront source build는 기존 exact-source local operator approval이 계속 필요하다. 어떤 HTTP/env flag도 그 권한을 만들지 않는다. fixed worker 자체는 build NOT_REQUIRED이며 가짜 compiler 성공 로그를 만들지 않는다.

## 1. 기존 저장소에서 설치하고 좁게 검사

압축본 전용 patch와 shared integration hunk를 root가 통합한 저장소 루트에서 실행한다. `py -3.12`가 선택하는 기존 64-bit Python3.12 또는 기존 venv를 명시한다. PowerShell 실행 정책은 조직/사용자 로컬 정책을 따르며 스크립트가 우회하지 않는다.

```powershell
# 명시 설치: 기존 pyproject의 pinned dependency만 사용한다.
.\tools\law_native\windows.ps1 -Install

# 이미 있는 동일 환경: 설치를 자동 반복하지 않는다.
.\tools\law_native\windows.ps1 -Venv 'C:\path\to\existing-venv'

# 네트워크 없는 설치: 사전에 같은 Windows/Python용으로 준비한 wheelhouse를 지정한다.
.\tools\law_native\windows.ps1 -Install -Wheelhouse 'D:\wheelhouse'

# 실제 spatial pair와 기존 Simulation cold owner까지 실행하는 별도 명령이다.
.\tools\law_native\windows.ps1 -RunSpatial

# 실제 Qt 정상/좁은 창의 별도 검사다.
.\tools\law_native\windows.ps1 -RunGui
```

script는 설치를 요청한 경우에만 새 `.venv-law-native`를 만든다. default 검사는 point/retention/J2/owned-finally/기존 fit-CAS이며 spatial FE/GUI는 위 switch로 별도 요청한다. pip isolated/report와 stdout/stderr, PowerShell transcript, command·runtime·종료 receipt를 `runs/law-native-windows-<고유ID>`에 남긴다. 실패/timeout/SKIP은 PASS로 바꾸지 않는다. FELUPE가 없으면 actual FE 검사는 SKIP이고 실행 worker는 REJECTED/FE_execution NOT_RUN을 기록한다. 모듈 import만으로 Windows가 검증됐다고 하지 않는다.

원 pyproject pins: Python>=3.12; numpy2.3.5, scipy1.17.0, felupe11.1.3; GUI PySide6 6.9.1/matplotlib3.10.8; tests pytest8.4.2. 다른 deps는 원 pyproject를 따른다. Linux 작성 환경의 버전과 이 배포 pin이 다를 수 있으므로 `evidence/environment.json`을 같이 읽는다. 별도 버전 upgrade는 이 pair의 검증 밖이다.

FELUPE 11.1.3 공식 pure Python wheel의 배포 hash(이 환경에서 다운로드/검증한 binary가 아니라 공식 게시값):

```
felupe-11.1.3-py3-none-any.whl
SHA256 0136a783abc010f89d12f33409aa9b7b9d0701a5998b045f7445adb380a58a19
https://pypi.org/project/felupe/11.1.3/#files
```

worker는 실제 실행될 Python executable hash, platform/ABI, FELUPE version/source file hashes, NumPy/SciPy binary file hashes와 license declaration을 `runtime.json`에 기록한다. 공식 wheel 게시 hash와 실행 환경의 loaded binary hash는 서로 다른 대상이다. 이 ZIP에 제3자 binary는 없다. FELUPE GPL-3.0-or-later이고 원 프로젝트 최상위 LICENSE가 첨부 baseline에는 없으므로 프로젝트의 재배포 허가까지 추정하지 않는다. 무료 로컬 사용 경로와 외부 재배포 license 검토를 분리한다.

## 2. FreeCAD와 연구 service Python의 분리

FreeCAD Python ABI에 연구 venv의 SciPy/PySide6 DLL을 억지로 넣지 않는다. native owner는 기존 FreeCAD 환경에서 대상 geometry/mesh/metadata를 읽고 고정 interface를 적용한다. 실제 FE는 기존 연구 Workbench/JobManager가 연구 Python에서 실행한다. target 문서에 있는 CalculiX native solver는 문맥 identity일 뿐 이 경로의 실제 solver가 아니다.

기존 registered Pre + local service 사용 시에는 Material 창에서 정확한 saved revision으로 전송한다. standalone 실제 native 검사에서는 다음 두 명령을 사용한다. 첫 명령의 output은 반드시 새 경로여야 한다.

```powershell
$P = '.\.venv-law-native\Scripts\python.exe'
& $P tools/law_native/owned_check.py --output runs/law-save-check --timeout 30 -- `
  $P tools/law_native/save_source.py --output runs/law-saved-source --model drucker_prager_linear

& $P tools/law_native/run_freecad_smoke.py `
  --freecad 'C:\실제 설치 경로\bin\FreeCAD.exe' `
  --source runs/law-saved-source/source-snapshot.json --output runs/law-freecad-smoke
```

실제 존재하는 FreeCAD 실행 파일을 명시해야 한다. 사용자 작업 중인 FreeCAD 프로세스에 연결해 검사하거나 종료하지 않는다. 검사기는 직접 연 새 GUI process 두 개를 순차 소유한다. 첫 process에서 실제 ObjectsFem/27절점8Hex8 생성→기존 owner region→순수 preview→invalid raw 저장→Apply→기존 Material 불변→freeze→실제 Undo/Redo→FCStd 저장, 두 번째 새 process에서 FCStd 열기→새 기존 native owner→보존 assignment hash 읽기를 검사한다. 전체 실제 FEM 계산은 이 검사에서 하지 않는다.

FreeCAD의 기존 문서가 이미 있는 process에서는 smoke가 변경/종료를 거절한다. config의 고유 token은 smoke process 귀속 확인용이지 build 권한이 아니다. native smoke의 fixed 순서 mesh와 실제 FreeCAD SMESH convention이 다르면 FAIL로 남으며 node를 재정렬해 통과시키지 않는다.

실제 frozen 파일은 `runs/law-freecad-smoke/apply/frozen-simulation.json`이다. 적용 결과를 FE로 보내는 별도 명령:

```powershell
& $P tools/law_native/owned_check.py --output runs/law-fe-owned --timeout 240 -- `
  $P examples/material-tests/law-native/fe_workflow.py `
  --input runs/law-freecad-smoke/apply/frozen-simulation.json --output runs/law-fe-owner
```

이때 FE_workflow는 기존 Simulation 문서 save→명시 evaluate→실제 FE와 point pair 결과→save→owner shutdown→새 owner cold read를 실행한다. public `--input` 없이 세 법칙의 synthetic mesh를 실행하는 검사와 native saved assignment 입력을 쓰는 위 검사를 구분한다. Neo/SLS native 검사에는 첫 `save_source.py --model neo_hooke` 또는 `single_branch_maxwell`로 새 source/output을 만들고 같은 분리 단계를 따른다.

## 3. 기존 앱에서 열기

이미 실행 중인 로컬 service 주소를 그대로 사용한다. 새 localhost 제품 UI나 새 웹 앱을 만들지 않는다.

```powershell
& $P -m apps.research.material_window --service $env:CAELAB_SERVICE_URL
# 또는 기존 저장 Material ID를 명시
& $P -m apps.research.material_window --service $env:CAELAB_SERVICE_URL --document-id '실제 M...'
```

Material 법칙 메뉴의 DP/명시 Neo-Hooke/단일 branch SLS 창을 이용한다. 실제법칙을 고르고 계수/단위/시간/F/초기 상태를 편집한 뒤 저장한다. evaluate와 독립 tangent, Numerical Plan/채택을 수행한 뒤 FE할당 검토로 넘어간다. normal/narrow, 한국어 font/큰 곡선, Enter/Esc/Undo/dirty close, pending lost-ack 버튼, 다른 Material 창과 preview 취소의 비간섭은 Sol/root가 실제 Qt/FreeCAD에서 추가 인수해야 한다. `-RunGui`는 관련 작은 자동 검사이며 전체 C01 사용성 인증이 아니다.

## 4. 종료·오류·보존 읽기

`owned_check.py`는 직접 Popen한 PID/Windows Job 또는 POSIX process group만 소유한다. 성공/실패/timeout/예외의 모든 경로에서 finally로 정리하고 `CONFIRMED_REAPED` 또는 정확한 `UNKNOWN`을 남긴다. 프로그램명 전체 종료, 기존 사용자 PID 가져오기, 기존 native 창 강제 종료는 없다. underlying JobManager/worker의 기존 cancellation/close 경계를 재사용한다. 실행 제한은 명령에 명시되며 TIMEOUT을 실패 로그와 함께 보존한다.

보존 결과 읽기는 FELUPE나 compiler 없이 가능하다. source snapshot의 예전 절대 경로가 남아 있어도 cold 읽기에 접근하지 않는다. 새 Apply/계산은 현재 owner source 및 현재 trusted kernel과 재대조한다. source 삭제 후 ‘기존 결과 읽기’와 ‘새 계산 허용’을 같은 정책으로 만들지 않는다.

공식 참고: https://docs.python.org/3.12/using/windows.html , https://pypi.org/project/felupe/11.1.3/ . 설치 경로의 실제 동작은 이 인도에서 NOT_RUN이며 위 명령의 실제 receipt로 확인해야 한다.
