# 추가 구매 없는 Windows native 빌드

## 결론과 필요한 환경

전달받은 runtime은 ParaView 6.2.0, Qt6Core.dll 6.9.0.0, Python 3.12, Windows x64다.
그 ZIP의 bin DLL만으로 C++ plugin을 컴파일할 수 없다. 필요한 것은 해당 빌드와 맞는
ParaView include/import library/CMake config, Qt 6.9.0 Core/Gui/Widgets 개발 파일,
x64 MSVC compiler/Windows SDK/CMake/Ninja다. Qt source checkout 준비에는 Git/Perl과 Qt 공식 문서가 지정한 Python도 필요하다. Qt harness에는 Qt Test도 필요하다.
Python 자체의 SDK/Qt Python binding은 이 bridge를 위해 추가하지 않는다.

정확한 해당 stock binary용 공식 standalone SDK 다운로드 존재는 확인하지 못했다.
다른 버전 SDK를 맞는 것처럼 표시하지 않는다. SDK와 runtime의 동일 빌드 관계를
증명할 수 없다면 **Qt6.9.0 + ParaView6.2.0을 같은 toolchain으로 나란히 빌드하여
그 runtime과 그 development install을 함께 사용하는 경로**가 재현 가능한 대안이다.
기존 설치를 덮어쓰지 않는다. 공식 source 기반이며 상용 SDK 구매가 전제되지 않는다.

Windows 통합 검토에서 [공식 binary-compatible guide](https://gitlab.kitware.com/paraview/paraview-plugin-windows-binary-compatible-guide)를
확인했다. 검토한 guide commit `49ec4a63`에는 v6.2.0용 테스트 configuration이 없다.
다른 버전 configuration을 그대로 실행하지 않는다. 정확한
[v6.2.0 superbuild CI](https://gitlab.kitware.com/paraview/paraview-superbuild/-/tree/v6.2.0/.gitlab/ci)의
`download_qt6.cmake`는 Qt 6.9.0·MSVC2022·build stamp 202503301022를 지정하고,
`download_qt6_hashes.cmake`는 대응 Qt archive hash를 제공한다. 해당 CI의 Qt URL은
Kitware 내부 경로이므로 접근이나 다운로드를 가정하지 않는다. 공개 Qt 배포와
SDK/runtime의 실제 build 관계를 확인해야 하며, 같은 버전 문자열만으로 ABI
호환이나 설치된 stock bundle과의 동일성을 인정하지 않는다.

## 무료 도구와 라이선스의 범위

Microsoft의 공식 안내는 Visual Studio Build Tools로 OSS C/C++ 의존성을 빌드하는
무료 사용 범위를 설명한다. 이는 모든 기업의 모든 폐쇄형 C++ 개발에 무조건 무료인
Visual Studio IDE 사용권을 준다는 뜻이 아니다. 여기의 신규 plugin은 BSD-3-Clause
소스로 제공한다. 설치하는 Build Tools와 Windows SDK의 현행 약관은 그대로 적용된다.

Qt의 open-source 경로로 동적 Core/Gui/Widgets 등을 사용한다. LGPL/GPL 선택,
실제로 사용하는 Qt 모듈과 도구의 license, third-party notice를 확인해야 한다.
Qt SDK 전체를 제품 ZIP에 재배포하지 않는다. 바이너리 배포 시 실제 해당 Qt 버전의
license 사본/notice, 대응 소스 제공 방법, 수정된 Qt 교체/재링크 및 허용된 debugging에
관한 의무를 충족해야 한다. 독점 상용 Qt SDK를 사용해야 하는 설계가 아니다.
새 CaePostExit 코드의 BSD license는 native/post_exit/LICENSE에 있다. 원 프로젝트나
ParaView/VTK/Qt 전체를 재라이선스한 것은 아니다. NOTICE_KO.md도 확인한다.

## 공식 소스로 matching runtime/SDK 준비

공식 Qt 6.9.0 source archive 또는 공식 qt5 저장소의 v6.9.0 tag를 사용한다. 아래는
같은 x64 Native Tools 환경에서 수행하는 source-build 명령 구성이다. 기존 환경에서
실행한 기록이 아니며 필요한 모듈/배포 의존성은 CMake 진단을 보존하여 확인한다.

```powershell
# 공식 Qt 소스 checkout. 기존 설치 디렉터리와 분리한다.
git clone --branch v6.9.0 https://code.qt.io/qt/qt5.git C:\cae-build\qt-src
cd C:\cae-build\qt-src
perl init-repository --module-subset=qtbase,qttools,qtsvg,qt5compat
mkdir C:\cae-build\qt-build
cd C:\cae-build\qt-build
C:\cae-build\qt-src\configure.bat -opensource -confirm-license -release -shared -nomake examples -nomake tests -prefix C:\cae-tools\qt-6.9.0
cmake --build . --parallel
cmake --install .

# 정확한 ParaView tag와 그 tag의 VTK submodule을 함께 받는다.
git clone --branch v6.2.0 --recursive https://gitlab.kitware.com/paraview/paraview.git C:\cae-build\paraview-src
cmake -S C:\cae-build\paraview-src -B C:\cae-build\paraview-build -G Ninja `
  -DCMAKE_BUILD_TYPE=Release -DPARAVIEW_USE_QT=ON -DPARAVIEW_QT_MAJOR_VERSION=6 `
  -DPARAVIEW_USE_PYTHON=ON -DPARAVIEW_USE_MPI=OFF -DPARAVIEW_ENABLE_WEB=OFF `
  -DPARAVIEW_BUILD_SHARED_LIBS=ON -DPARAVIEW_BUILD_TESTING=OFF `
  -DPARAVIEW_INSTALL_DEVELOPMENT_FILES=ON `
  -DCMAKE_PREFIX_PATH=C:\cae-tools\qt-6.9.0 `
  -DPython3_ROOT_DIR=C:\cae-tools\Python312 `
  -DCMAKE_INSTALL_PREFIX=C:\cae-tools\ParaView-6.2.0-matched
cmake --build C:\cae-build\paraview-build --parallel
cmake --install C:\cae-build\paraview-build
```

Python312는 x64 Python 3.12 development files를 가진 공식 배포를 사용하고 ParaView의
CMake가 그 interpreter/library/include를 실제로 선택했는지 확인한다. plain CMake
install은 완전한 portable runtime packaging을 보장하지 않는다. Qt runtime/platform
plugin, Python runtime 및 필요한 모듈을 같은 빌드에서 배포하고 정상 시작을 검증한다.
ParaView superbuild/packaging을 사용하는 경우도 exact tag/Qt/Python/toolchain 및
CMakeCache와 source commit/submodule 목록을 보존한다. Qt5/Qt6를 섞지 않는다.

위 설정은 이 plugin의 무료 기반 경로다. 기존 배포판의 모든 선택 plugin/reader를
동일하게 재현했다고 주장하지 않는다. 실제 사용자 외부/계산 결과 reader와 복구
작업을 matching build에서도 확인해야 한다. Qt installer를 사용하는 경우에도
open-source 배포를 선택하고 정확 6.9.0 개발 파일을 확보했는지 확인한다.

## plugin 빌드

```powershell
# PATH에는 동일 Qt SDK bin, 동일 ParaView runtime bin을 먼저 둔다.
$env:PATH = 'C:\cae-tools\qt-6.9.0\bin;C:\cae-tools\ParaView-6.2.0-matched\bin;' + $env:PATH
.\native\post_exit\Build-PostExit.ps1 `
  -ParaViewDir C:\cae-tools\ParaView-6.2.0-matched\lib\cmake\paraview-6.2 `
  -Qt6Dir C:\cae-tools\qt-6.9.0\lib\cmake\Qt6 `
  -BuildDir C:\cae-build\post-exit-build-r01 -Python C:\cae-tools\Python312\python.exe -RunQtHarness
```

CMake는 ParaView 6.2.0 EXACT, Qt 6.9.0 EXACT, x64, Release, dynamic linking을 요구한다.
Ninja/MSVC가 아니거나 debug CRT 등 불일치를 runtime 파일명만 보고 허용하지 않는다.
Qt harness 성공은 실제 ParaView 성공이 아니다. 별도 프로세스에서 만드는 자신의
Qt 창만 사용한다. Qt 대화상자 캡처는 qt-captures에 저장하며 실제 ParaView 캡처와
명확히 구분한다.

통합본은 기존 `scripts/native_check.py`로 ctest와 그 자식 검사 프로그램을
한 Windows Job에 묶는다. 성공·실패·시간 초과의 로그와 정리 기록은 새
`core-test-job` 및 `qt-test-job` 폴더에 남긴다. 이 경로는 별도 Job 실행기 구현이 아니다.

## artifact/version 기록

SDK 준비 담당이 `cae.post-exit-sdk/1` JSON을 작성한다. `runtime_relationship`은 실제
동일 build이면 `same-sdk-build`, 공식 일치 SDK 증빙이 있는 경우에만
`official-matching-sdk`다. `files`는 해당 ParaView/Qt CMakeCache/config 및 build/source
증빙 파일의 **절대경로: SHA256** 사전이다. 실행하지 않은 빌드를 기록하면 안 된다.

```powershell
# SDK 파일 경로는 실제 사용한 파일로 지정한다.
$files = @{}
@('C:\cae-build\paraview-build\CMakeCache.txt','C:\cae-build\qt-build\CMakeCache.txt') | ForEach-Object {
  $files[$_] = (Get-FileHash $_ -Algorithm SHA256).Hash.ToLowerInvariant()
}
@{schema='cae.post-exit-sdk/1'; runtime_relationship='same-sdk-build'; files=$files} |
  ConvertTo-Json -Depth 5 | Set-Content -Encoding utf8 C:\cae-build\sdk-evidence.json

# 실제 build 산출물은 새 artifact 폴더로 복사하고 아래를 실행한다.
python scripts/post_exit_artifact.py `
  --plugin C:\cae-build\artifact-r01\CaePostExit.dll `
  --runtime C:\cae-tools\ParaView-6.2.0-matched `
  --build-info C:\cae-build\post-exit-build-r01\cae-post-exit-build-info.json `
  --sdk-evidence C:\cae-build\sdk-evidence.json
```

스크립트는 PE64 DLL, exact build 정보, SDK 파일 hash, 실제 runtime DLL/EXE hash를
검사하여 `.dll.manifest.json`을 생성한다. 기존 manifest는 덮어쓰지 않는다.
Hash는 동일성 증거이지 ABI 호환/메뉴 입력/저장 성공 증명이 아니다. native_acceptance는
NOT_RUN으로 남으며 수용 검사 증거를 별도로 첨부해야 한다.

## 이 환경에서 남은 작업

Pro 작성 환경은 Linux/GCC/Python3.13이며 Qt/ParaView SDK가 없었다. 그 입력 ZIP에는
`scripts/native_check.py`가 없었지만 현재 Windows 저장소에는 기존 실행기가 있다.
Windows 통합본에서도 MSVC build, Qt6.9 harness, 실제 ParaView6.2 native check는
아직 미실행이며 이 인도물에 Windows DLL을 넣지 않았다. exact SDK/runtime을
준비한 뒤 ACCEPTANCE_KO.md의 실창 검사를 수행해야 한다.
