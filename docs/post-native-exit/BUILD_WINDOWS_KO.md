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

2026-10-15 Windows 검증에서는 PATH 밖에 설치된 VS2022 Community/MSVC 19.43,
Windows SDK 10.0.22621, CMake 3.30.5를 실제로 찾았다. 공식 공개 Qt repository의
6.9.0/MSVC2022 archive 네 개(qtbase, qttools, qtsvg, qt5compat)를 위 v6.2.0 CI의
SHA256과 대조해 별도 개발 prefix에 풀었다. Core/Gui/Widgets runtime DLL은
기존 stock ParaView DLL과 SHA256도 같았다. 이것은 Qt 일치 증거이며 ParaView
include/import library의 일치 증거를 대신하지 않는다. 공식 ParaView 6.2.0 release
source archive는 superbuild의 MD5와 대조했으며 별도 runtime/SDK 빌드에 사용한다.

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
  -DPARAVIEW_PLUGIN_DISABLE_XML_DOCUMENTATION=ON `
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

실제 Windows 구성의 첫 실패는 Qt6에 없는 `xmlpatterns`/미설치 `xsltproc`를
플러그인 도움말 생성이 요구한 경우였다. 위 공식 옵션은 선택적 XML 도움말 생성만
끈다. 원 실패 로그와 재구성 로그는 별도로 보존한다. 또한 한글 MSVC 출력 접두어가
CMake에서 잘못 해석돼 Ninja의 헤더 의존성이 0개인 경우를 확인했다. 이 호스트는
공식 `CMAKE_PROJECT_INCLUDE` 훅에서 실제 관측한 `CMAKE_CL_SHOWINCLUDES_PREFIX`만
지정해 해결했다. 새 소규모 빌드에서 CloseGate 216개·Qt test 290개의 헤더 의존성을
확인했다. 사용자 VS 언어, 시스템 코드 페이지 또는 전역 환경은 변경하지 않았다.

## plugin 빌드

ParaView SDK를 준비하는 동안에는 같은 Qt 개발 파일로 종료 이벤트 하네스만
분리해서 빌드할 수 있다. 이 모드는 ParaView plugin이나 SDK manifest를 만들지 않는다.

```powershell
cmake -S native/post_exit -B C:\cae-build\qt-harness-r01 -G Ninja `
  -DCAE_EXIT_QT_HARNESS_ONLY=ON -DCMAKE_BUILD_TYPE=Release `
  -DQt6_DIR=C:\cae-tools\qt-6.9.0\lib\cmake\Qt6
cmake --build C:\cae-build\qt-harness-r01
# 동일 Qt bin/platform plugin 경로를 설정한 후 기존 owned Job runner로 실행한다.
python scripts/native_check.py --timeout 120 --output-dir C:\cae-checks\qt-r01 -- `
  C:\cae-build\qt-harness-r01\tests\cae_exit_qt.exe
```

Windows 하네스는 Ctrl+Q 전달 전에 창 활성화를 기다리고, SC_CLOSE의 비동기
닫기 전달을 기다린다. Alt+F4는 자기 HWND의 Windows system-key message 경로다.
현재 UI thread의 keyboard-state snapshot만 잠시 바꿨다가 즉시 복원한다. 전역 입력이나
다른 창의 keyboard state를 건드리지 않는다. 실제 사용자 키보드 입력 수용은 별도다.

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
Windows 통합 검증에서는 dependency-free transaction executable과 C/Python ABI DLL을
실제 MSVC로 빌드해 2개 검사를 통과했다. 실제 Qt6.9 C++ 하네스도 빌드했다. 최초
12개 XML case 중 2개 입력 전달 검사가 실패했고, 위 하네스 동기화/메시지 교정 후
그 두 검사만 재실행해 통과했다. 원 실패 로그를 보존했으며 각 실행의 Job은 비었다.
한글 대화상자는 실제 QWidget grab으로 정상/좁은 부모 창 크기에서 확인했다.
이 결과는 ParaView plugin의 컴파일이나 실제 ParaView6.2 종료 수용을 뜻하지 않는다.
SDK/runtime을 완성한 뒤 ACCEPTANCE_KO.md의 실창 검사를 수행해야 한다.
