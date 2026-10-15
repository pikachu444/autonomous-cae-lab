# 같은 빌드의 후처리 실행 파일 회수

이 묶음은 개발 중인 ParaView와 종료 plugin을 같은 빌드 그대로 옮겨 확인하기 위한
자료입니다. 일반 PC용 설치 프로그램이 아니며 실제 File → Exit, 깨끗한 PC 설치,
공학적 승인 완료를 뜻하지 않습니다. 다른 stock ParaView에 plugin DLL만 붙이지 않습니다.

## 빌드한 환경에서 묶기

기존 Windows SDK 검사 전체가 성공한 뒤, 같은 작업 폴더와 공식 Python을 지정합니다.
7-Zip은 이미 설치된 공식 도구를 사용합니다. 스크립트는 다운로드·설치·업로드를 하지 않습니다.

```powershell
./scripts/package_post_runtime_windows.ps1 -WorkRoot $env:POST_NATIVE_ROOT `
  -Python $python -SevenZip 'C:\Program Files\7-Zip\7z.exe'
```

새 `recovery` 하위 폴더만 만들며 기존 폴더가 있으면 거절합니다. 같은 runtime 전체,
plugin과 기존 manifest, Qt 플랫폼 DLL, 공식 CPython 3.12.10의 실행 파일·표준 라이브러리·
확장 DLL, 고정 NumPy 2.3.5 wheel의 실행 자료와 라이선스를 넣습니다. 다른 Python 패키지,
사용자 설정·프로필·프로젝트·자격증명·시스템 DLL을 추가로 수집하지 않습니다.
빌드 출처, 입력 URL·SHA, 소프트웨어 라이선스와 Qt SBOM도 보존합니다.

`post-runtime.7z.001`부터 이어지는 분할 파일은 각각 1890 MiB 이하입니다.
`package-receipt.json`의 파일 크기·SHA와 `post-runtime/files.json`의 전체 파일 목록을
함께 확인합니다. 압축 검사와 staging의 기존 artifact 검증이 성공해야 receipt를 씁니다.
실패 시 새 작업 폴더를 보존해 원인을 확인하고 원 빌드를 덮어쓰지 않습니다.

root 담당자는 이 파일과 receipt만 기존 공개 저장소의 미공개 draft release에 회수용으로
보관합니다. 이 스크립트는 release를 만들지 않습니다. Actions artifact/cache는 사용하지 않습니다.

## 내려받은 환경에서 확인

모든 분할 파일과 receipt를 같은 새 폴더로 받고 각 SHA를 대조한 뒤 첫 파일을 풉니다.

```powershell
& $sevenZip x .\post-runtime.7z.001 -oC:\CAE\post-check
```

풀린 `post-runtime`을 `$bundle`로 두고 기존 연구 Python에서 같은 검증을 실행합니다.
기존 manifest는 변경하거나 새로 만들지 않습니다.

```powershell
& $caePython -c "from pathlib import Path; from apps.desktop_post.native_exit_abi import verify_artifact; import sys; b=Path(sys.argv[1]); verify_artifact(b/'plugin/CaePostExit.dll', b/'runtime')" $bundle
$env:CAE_POST_EXIT_PLUGIN = Join-Path $bundle 'plugin/CaePostExit.dll'
$env:CAE_POST_PARAVIEW_ROOT = Join-Path $bundle 'runtime'
```

기존 연구 프로그램과 같은 서비스·workspace에서 `runtime/bin/paraview.exe`를 선택합니다.
관리 저장·재열기 절차는 기존 [저장 안내](https://github.com/pikachu444/autonomous-cae-lab/blob/main/docs/post-exit/USAGE_KO.md)를 따릅니다.
이 환경 변수는 확인용 프로세스에만 적용하고 작업 후 복원합니다.

Python 표준 라이브러리는 `runtime/bin/Lib`, 확장 모듈은 `runtime/bin/DLLs`에 있습니다.
이전 runner의 Python 경로는 provenance 기록일 뿐 실행 경로로 설정하지 않습니다.
연구 Python을 시작하기 전에 전역 `PYTHONHOME`를 바꾸면 기존 환경을 깨뜨릴 수 있습니다.
회수 후 기존 pin 검증과 별도로, 소유한 새 프로세스에서 Python·NumPy import와 plugin
load를 확인해야 합니다. 패키징의 SHA 검사만으로 DLL load 성공을 주장하지 않습니다.

시스템 CRT는 임의 복사하지 않습니다. Windows x64와 빌드 도구보다 같거나 새로운
[공식 Visual C++ v14 재배포 패키지](https://learn.microsoft.com/en-us/cpp/windows/latest-supported-vc-redist?view=msvc-170)가
필요합니다. 빌드 당시 컴파일러·CRT 버전은 `sources.json`에 보존합니다. 해당 PC의 설치와
실제 load는 별도 확인 대상이며 이 스크립트가 시스템을 변경하지 않습니다.

## 라이선스와 공식 소스

`licenses`의 LGPLv3·GPLv3 원문·Qt SBOM과 Python `LICENSE.txt`, NumPy dist-info의
licenses를 함께 보존합니다. GPLv3 원문은 저장소의 기존 공개 사본을 그대로 복사합니다.
공식 입력의 URL·해시는 `sources.json`과 `provenance/inputs.json`에 있습니다.
ParaView 소스는 해당 고정 tar.xz, Python은
[3.12.10 공식 배포](https://www.python.org/downloads/release/python-31210/), Qt는
[6.9.0 공식 소스](https://download.qt.io/archive/qt/6.9/6.9.0/single/), NumPy는
[2.3.5 원 소스](https://github.com/numpy/numpy/tree/v2.3.5)를 참조합니다.
Qt는 교체 가능한 공유 DLL로 유지하며 라이선스·저작권 고지·SBOM을 제거하지 않습니다.
이 개발 회수 절차를 일반 제품 배포나 모든 제3자 라이선스 의무의 완료로 해석하지 않습니다.
