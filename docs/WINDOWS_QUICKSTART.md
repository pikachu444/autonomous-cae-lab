# Windows에서 Research 데스크톱 시작하기

`Start-CAE-Lab.cmd`의 기본 진입은 **Qt Runner 창**이다. Numerical·Expert·Data·
PDE 등 다른 도구도 `-Tool`로 직접 시작한다. 각 창은 같은 로컬 서비스의
문서와 작업을 사용하므로, 따로 시작한 연구를 기존 도구 간 이동으로 이어갈 수 있다.
[Research 실행 안내](../apps/research/README.md)에 전체 도구와 선택 인수가 있다.

## 시작

1. 저장소의 **Code → Download ZIP**으로 내려받아 사용자 폴더에 압축을 푼다.
2. **Start-CAE-Lab.cmd**를 더블클릭한다. 첫 실행은 기존 설치기를 통해 uv,
   전용 Python 3.12, 수치·재료 패키지와 Qt Research 의존성을 준비한다.
3. Runner에서 기존 작업을 열거나, 아래 명령으로 원하는 도구를 직접 연다.

Windows 10/11 x64의 기본 Windows PowerShell 5.1을 사용한다. 기본 Research
진입에는 WSL, Git, 미리 설치한 Python, 관리자 권한이 필요하지 않다. 설치에는
GitHub와 Python 패키지·런타임 다운로드 서버에 대한 인터넷 접근이 필요하다.
압축을 푼 소스 폴더는 계속 보관한다. 설치된 환경이 그 코드를 사용한다.

저장소 폴더의 PowerShell에서:

```powershell
.\Start-CAE-Lab.cmd -Tool numerical
.\Start-CAE-Lab.cmd -Tool expert
.\Start-CAE-Lab.cmd -Tool data
.\Start-CAE-Lab.cmd -Tool pde
.\Start-CAE-Lab.cmd -Tool simulation
```

Runner는 기본 선택일 뿐이다. 연구를 Runner나 Material에서 먼저 만들 필요는 없다.
Data의 표·채널, Numerical의 연구 계획, Expert의 논의, PDE의 모델 등 필요한
도구에서 시작한다. FreeCAD CAD/FE와 ParaView Post는 기존
`start_cae_pre.ps1` / `start_cae_post.ps1`와 각 도구의 이동 명령을 통해
별도 네이티브 프로세스로 연다. Qt 창 안에 이 프로그램들을 합치지 않는다.

## 저장한 문서나 작업으로 바로 들어가기

```powershell
.\Start-CAE-Lab.cmd -Tool numerical -DocumentId DOCUMENT_ID
.\Start-CAE-Lab.cmd -Tool expert -DocumentId DOCUMENT_ID
.\Start-CAE-Lab.cmd -Tool runner -JobId JOB_ID
```

`DOCUMENT_ID`와 `JOB_ID`는 실제 저장한 ID로 바꾼다. ID를 생략하면 해당
도구에 진입한다. Runner는 작업 ID, 나머지 Research 도구는 문서 ID를 받는다.
파일명을 문서 ID로 바꾸거나 기존 파일을 자동으로 이름 변경하지 않는다.

같은 서비스에서 열면 기존 문서 소유자가 편집·저장·재열기를 처리한다. 선택한
작업의 원본과 결과로 이동하는 명령도 기존 연결을 사용한다. 결과를 여는 것으로
새 계산을 제출하지 않는다. 이 시작기 변경 자체가 모든 도구의 편집·해석·후속
연구 경로를 완성했다는 뜻은 아니다.

## 창 없이 준비하기

| 실행 | 동작 |
|---|---|
| `Start-CAE-Lab.cmd` / `-Tool …` | Qt 의존성 준비 → 서비스 시작 또는 확인 → 선택한 Qt 창 |
| `-NoBrowser` | 명시한 선택 의존성만 준비하고 서비스 시작·확인; 창 없음 |
| `-PrepareOnly` | Qt와 서비스 준비 후 도구·문서/작업 선택을 반환; 창 없음 |
| `-InstallOnly` | 명시한 의존성 설치만 수행; 서비스·창 없음 |

`-InstallOnly -PrepareOnly`도 설치만 한다.
`-NoBrowser -PrepareOnly`는 준비 결과를 반환하지만 Qt를 자동 추가하지 않는다.
기존 Research helper의 `-PrepareOnly`는 계속 Qt를 준비한다.

```powershell
# Qt를 포함하여 설치만 준비
.\Start-CAE-Lab.cmd -InstallOnly -ResearchUI

# 이후 Qt 창에서 사용할 서비스를 창 없이 준비
.\Start-CAE-Lab.cmd -NoBrowser -ResearchUI

# 이 도구와 문서 선택을 포함한 준비 결과 반환
.\Start-CAE-Lab.cmd -Tool numerical -DocumentId DOCUMENT_ID -PrepareOnly
```

인수가 있는 CMD wrapper는 추가 pause를 하지 않고 자식의 종료 코드를 전달한다.
NoBrowser·PrepareOnly·InstallOnly headless 모드는 비대화형이다.
일반 Qt 시작 오류는 오류 창을 표시할 수 있다. 인수 없이 더블클릭한 실행이
실패했을 때만 CMD가 진단 확인용 키 입력 대기를 추가한다.
Python 직접 실행의 옵션은 `--prepare-only`처럼 전체 이름을 쓴다.

## 설치 범위와 도구별 실행환경

기본 Qt 실행은 기존 `research-ui` 의존성인 PySide6 6.9.1과
Matplotlib 3.10.8을 자동 요청한다. 현재 설치 기록이 맞으면 기존 환경을 재사용한다.
설치기는 개인 Python·로그 경로를 쓰며 시스템 Python/PATH나 개발용 Python
환경을 바꾸지 않는다.

| 기능 | 준비 범위 |
|---|---|
| Qt Research 창과 기존 문서·작업 연결 | 기본 실행에서 `research-ui` 준비 |
| Data 파일 읽기와 저장 결과, SciPy 수치 기능 | 기존 기본·수치 패키지; 실제 계산에 필요한 모델 조건은 별도 |
| FELUPE 재료점 응력·탄젠트 | 기존 material 패키지; 다른 도구를 시작하기 위한 작업 선행조건은 아님 |
| FreeCAD/CadQuery, Gmsh/CalculiX | 별도 네이티브 설치와 해당 경로의 고정 upstream 필요 |
| Code_Aster, DOLFINx, MFront/MGIS, OpenCourant | 각 실행환경 필요; 기존 Linux/WSL 근거를 Windows 검증으로 바꾸지 않음 |
| Expert | 기존 ResearchUI 설치의 assist-core import 준비; 실제 추론은 설정된 공급자·모델 권한이 별도 |

기본 실행은 모델 공급자를 호출하거나 계정을 변경하지 않는다. CAD·AI를 쓰지 않는
문서 편집과 저장 결과 읽기에는 해당 프로그램 실행이나 AI 로그인을 요구하지 않는다.
GitHub ZIP에는 submodule 내용이 없으므로 네이티브 CAD 경로는 필요한 소스를 별도로
준비해야 한다. Qt 설치와 창 열기가 솔버 실행 가능성이나 공학적 승인까지 보증하지 않는다.

## 저장 위치와 서비스 재사용

- 전용 도구/Python/로그: `%LOCALAPPDATA%\AutonomousCAELab\windows-runtime`
- 계산·원본·결과: `%LOCALAPPDATA%\AutonomousCAELab\research-store`
- 선택적 운영자 설정: `%LOCALAPPDATA%\AutonomousCAELab\workbench-config.json`

다른 위치를 쓸 때는 관련 도구에 같은 포트·저장소·런타임을 전달한다. 공백과
한글 경로는 따옴표로 감싼다:

```powershell
.\Start-CAE-Lab.cmd -Tool numerical -Port 8770 -Store 'D:\CAE 연구\실험 자료'
.\Start-CAE-Lab.cmd -Tool data -Port 8770 -Store 'D:\CAE 연구\실험 자료'
```

서비스는 127.0.0.1에 연결하며 Qt 창을 닫아도 계속 실행된다. 재실행할 때 기존
프로세스와 리스너, 저장소, 소스, 설정, 의존성, 준비 상태가 맞으면 재사용한다.
다른 소스나 설정의 서비스에는 조용히 연결하지 않으며 임의로 종료·교체하지 않는다.
Qt 없이 시작한 서비스에 의존성을 추가하면 명시적인 재시작이 필요할 수 있다.

서버를 종료할 때는 실행 중인 작업을 확인한 후 기존 종료 스크립트를 사용한다.
이 명령은 해당 시작기가 소유한 서버만 종료하며 실행 중인 작업을 중단할 수 있다.

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\scripts\stop-windows.ps1 -Force
```

다른 포트/런타임으로 시작했다면 종료 시에도 같은 `-Port` / `-RuntimeRoot`를
지정한다. 새 시작기가 이 종료를 자동으로 실행하지는 않는다.

## 이번 변경의 확인 범위

CMD는 자신의 `setlocal` 범위에서만 상속된 `PSModulePath`를 비워,
PS7/Python 부모에서 시작해도 Windows PowerShell이 표준 모듈 경로를 구성하도록
한다. 호출자 환경은 반환 시 복원되며 사용자·전역 환경 설정은 쓰지 않는다.
기존 설치기와 해시·소유권 검사는 그대로다.

초기 `111a36f`의 Python 진입·이동, 충돌 서비스 거절, Qt 의존성 준비와
PrepareOnly 반환은 Codex의 Windows 실행 보고로 확인했다.
`0b22ccc`의 축약 옵션 거절도 확인됐고, 격리한 자식 환경의 launcher
검사에서는 exit 17과 dispatch가 맞았으며 남은 오류는 진단 줄바꿈 assertion이었다.
이번 소스에서 그 assertion과 CMD 환경 경계를 교정했다.

서비스 18766의 실제 Qt Runner와 저장된 Data 문서 생성·렌더는
**Codex Windows offscreen 확인**이다. OS 입력·DPI는 **NOT_RUN**이며,
이번 추가 교정의 **Pro 원격 실행도 NOT_RUN**이다. 최종 반환 커밋의 실행·통합은
Codex가 수행한다. 검사 명령과 대역의 범위는
[Research 안내](../apps/research/README.md#verify-this-launcher-change)에 있다.

Python 설치·의존성 관리는 기존 [uv 설치](https://docs.astral.sh/uv/getting-started/installation/)와
[관리형 Python](https://docs.astral.sh/uv/guides/install-python/) 경로를 재사용한다.
uv 고정 버전·SHA-256 검사와 각 패키지의 라이선스 적용은 그대로다.
오프라인 배포 묶음, Linux 계산 서버 확장, 개별 솔버 검증은 이 시작기 변경에
포함하지 않는다. 현재 전체 구현 과제와 다음 Numerical·Expert 작업은
[CURRENT_STATE](../CURRENT_STATE.md)에서 관리한다.
