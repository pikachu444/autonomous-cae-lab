# CAE Lab Windows Qt 조작 시안

이 폴더는 여섯 작업 공간의 Windows Qt Widgets 검토용 시안이다. 각 `Start-*.cmd`는 같은 `CAELab.exe`를 독립 프로세스로 열고 자기 종류의 예제 문서를 불러온다. 메뉴에서 새 문서를 만들거나 다른 문서를 열고 저장할 수 있다. 계산·솔버·전문가 생성 중 화면에 시연 자료로 표시된 기능은 실제 제품 실행의 완료 증거가 아니다.

## 배포 폴더에서 실행

압축을 푼 `CAELab` 폴더에서 원하는 실행 파일을 더블클릭한다.

| 실행 파일 | 기본 문서 |
|---|---|
| `Start-Preprocessor.cmd` | `examples/pre.caeprep` |
| `Start-Solver-Runner.cmd` | `examples/runner.caerun` |
| `Start-Postprocessor.cmd` | `examples/post.caepost` |
| `Start-Optimizer.cmd` | `examples/opt.caestudy` |
| `Start-Expert.cmd` | `examples/expert.caechat` |
| `Start-Workbench.cmd` | `examples/workbench.caeproject` |

`CAELab.exe`도 직접 실행할 수 있으며 기본 창은 Workbench다. 문서와 버전 기록의 기본 저장 위치는 실행 파일 옆의 쓰기 가능한 `user-data` 폴더다. Windows의 보호된 `Program Files` 아래에 설치하지 말고 사용자 문서 폴더 같은 쓰기 가능한 위치에서 시안을 실행한다. 예제를 열어 저장하면 기존 예제 파일을 수정할 수 있으므로 원본을 남기려면 **다른 이름으로 저장**을 사용한다.

## 개발 환경에서 빌드

이 저장소의 부모 작업 폴더를 기준으로 `work/qt-prototype-venv`에 Python 3.12가 준비되어 있다. 재현할 때는 `requirements.txt`를 설치하고 저장소를 editable로 연결한다.

```powershell
$python = '..\work\qt-prototype-venv\Scripts\python.exe'
& $python -m pip install -r prototypes\desktop-lab\requirements.txt
& $python -m pip install -e '.[material]'
& .\prototypes\desktop-lab\build.ps1 -Python $python -ValidateOnly
& .\prototypes\desktop-lab\build.ps1 -Python $python
```

위 명령의 현재 디렉터리는 `repo`다. 빌드 결과는 저장소 밖 부모 작업 폴더의 `work/native-dist/CAELab/`에 생긴다. 빌드 전 `examples/`에 표의 여섯 파일이 있어야 한다. `build.ps1`은 QtCharts 참조가 남아 있으면 중단하고, 빌드 후 QtCharts DLL/모듈이 포함되지 않았는지 확인한다. 실제 화면 조작 검증은 빌드와 별도다.

현재 고정 버전의 PyInstaller가 함께 집어넣는 ICU 78 DLL은 Qt 6.11.2가 요구하는 Windows ICU 함수와 맞지 않아 시작 시 QtCore 로드가 실패한다. 빌드 스크립트는 해당 두 DLL을 `work/native-build/excluded-icu/`로 옮기고 Windows 시스템 ICU를 사용한다. 이 조합은 현재 Windows 11에서만 실행을 확인했으며 다른 Windows 버전의 배포 검증을 대신하지 않는다.

라이선스와 출처는 `THIRD_PARTY_NOTICES.txt` 및 `licenses/`를 확인한다. 이번 시안의 Windows exe 경로를 만들었다는 사실은 상용 배포 조건이나 수치·솔버 결과를 검증했다는 뜻이 아니다.
