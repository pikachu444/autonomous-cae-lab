# Windows 설치와 실행

기본 Research 앱은 Windows 10/11 x64에서 실행합니다. CAD 전처리는 FreeCAD,
후처리는 ParaView를 별도로 사용합니다. 현재 배포본은 개발 버전입니다.

## 처음 설치하기

1. [소스 ZIP](https://github.com/pikachu444/autonomous-cae-lab/archive/refs/heads/main.zip)을 내려받습니다.
2. 쓰기 권한이 있는 폴더에 압축을 풉니다. ZIP 안에서 실행하지 마세요.
3. 압축을 푼 폴더의 `Start-CAE-Lab.cmd`를 더블클릭합니다.

처음 실행하면 전용 Python과 필요한 패키지를 준비한 뒤 **Runner** 창을 엽니다.
아직 계산한 작업이 없으면 목록이 비어 있습니다. 설치 중에는 인터넷이
필요합니다. 기본 Research 실행에는 관리자 권한, Git, 시스템 Python, WSL이 필요하지
않습니다. 설치 후에도 압축을 푼 소스 폴더는 남겨 두세요.

다음 실행부터는 같은 파일을 더블클릭하면 됩니다. 다른 도구를 바로 열려면
소스 폴더에서 PowerShell을 열고 아래 명령 중 하나를 실행합니다.

```powershell
.\Start-CAE-Lab.cmd -Tool numerical
.\Start-CAE-Lab.cmd -Tool expert
.\Start-CAE-Lab.cmd -Tool data
.\Start-CAE-Lab.cmd -Tool material
.\Start-CAE-Lab.cmd -Tool pde
.\Start-CAE-Lab.cmd -Tool study
```

`simulation`, `evaluation`, `runner`도 선택할 수 있습니다. 저장된 연구 문서는
`-DocumentId`, Runner 작업은 `-JobId`로 지정합니다. 창을 열지 않고 설치만 하려면
아래 명령을 실행합니다.

```powershell
.\Start-CAE-Lab.cmd -InstallOnly -ResearchUI
```

## CAD와 후처리 열기

기본 설치에는 FreeCAD, ParaView, Gmsh, CalculiX가 포함되지 않습니다.
기존 설치를 연결해 사용합니다. 개발 환경에서 확인한 native 버전은
FreeCAD 1.1.4, ParaView 6.2.0입니다.

아래 `C:\Tools\...`는 예시입니다. **실제로 설치한 실행 파일 경로로 바꾸세요.**
FreeCAD portable 설치라면 `bin` 폴더의 실행 파일을 지정합니다.

```powershell
.\scripts\start_cae_pre.ps1 -FreeCADExe 'C:\Tools\FreeCAD\bin\freecad.exe' -Source '.\examples\contact\two-feet.FCStd'
.\scripts\start_cae_post.ps1 -ParaViewExe 'C:\Tools\ParaView\bin\paraview.exe' -InputPath 'C:\MyResults\result.vtu'
```

첫 번째 명령에서 여는 CAD 예제는 저장소에 포함되어 있습니다. 두 번째 명령의 결과 파일
경로는 사용자가 가진 파일의 경로로 바꾸세요. 실제 메시 생성과 해석에는 해당 backend 설정도
필요합니다. [첫 사용 예제](USER_GUIDE_KO.md)와 [접촉 작업 안내](CONTACT_WORKFLOW.md)를 참고하세요.

일부 native 기능은 고정된 upstream 소스를 사용합니다. ZIP에는 submodule 내용이
포함되지 않으므로 해당 기능을 개발하거나 실행할 때는 Git으로 받습니다.

```powershell
git clone --recurse-submodules https://github.com/pikachu444/autonomous-cae-lab.git
```

이미 Git으로 받은 저장소에서는 `git submodule update --init --recursive`로 준비합니다.

## Expert와 MCP

Expert 창에서 자료와 질문을 저장할 때와 실제 AI 응답을 받을 때는 필요한 준비가 다릅니다.
기본 설치만으로 AI가 연결되지는 않습니다. 기존 구독을 사용하는 native 연결 화면은
개발 중이며, 추가 유료 API로 우회하지 않습니다.

PDF 읽기와 MCP 패키지가 필요하면 선택해서 설치합니다.

```powershell
.\Start-CAE-Lab.cmd -InstallOnly -ResearchUI -Documents -MCP
.\Start-CAE-Lab.cmd -NoBrowser -ResearchUI -Documents -MCP
```

이후 MCP 클라이언트에 [연결 설정 예시](../openscience/workbench.json.example)를 등록해야
합니다. 예시의 `python`은 아래 전용 환경의 실행 파일로 바꾸고, 작업 폴더는 저장소
루트로 지정합니다. 설치 명령을 실행해도 클라이언트에 자동으로 연결되지는 않습니다.

## 파일이 저장되는 곳

| 내용 | 기본 위치 |
|---|---|
| 전용 실행 환경 | `%LOCALAPPDATA%\AutonomousCAELab\windows-runtime` |
| Python 실행 파일 | 위 폴더의 `venv\Scripts\python.exe` |
| Research 문서와 결과 | `%LOCALAPPDATA%\AutonomousCAELab\research-store` |
| 로컬 연결 설정 | `%LOCALAPPDATA%\AutonomousCAELab\workbench-config.json` |

Research 창을 닫아도 공유 서비스는 남을 수 있습니다. 업데이트 후 서비스가 이전
코드나 설정을 사용한다고 나오면 작업을 저장하고
[서비스 종료·재실행 안내](WINDOWS_QUICKSTART.md#저장-위치와-서비스-재사용)를 따르세요.
다른 계산이 실행 중인 서비스를 임의로 종료하지 마세요.

설치 오류는 열린 콘솔의 마지막 오류와 실행 명령부터 확인합니다. `NOT_CONFIGURED`는
필요한 backend 또는 Expert 연결이 설정되지 않았다는 뜻입니다. 자세한 옵션과 복구는
[Windows 상세 안내](WINDOWS_QUICKSTART.md)에 있습니다. 오류를 공유할 때는 인증정보와
회사 자료를 제외해 주세요.
