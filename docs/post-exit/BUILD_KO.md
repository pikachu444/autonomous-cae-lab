# 종료 plugin 빌드와 확인

기존 actual Pro의 C ABI·Qt/ParaView plugin과 관리 저장 관문을 재사용한다.
Sol은 종료 후속 처리의 수명 교정과 전용 회귀·창 확인을 맡았다. 별도 종료 앱,
대체 QAction, 새 저장 형식은 추가하지 않았다.

## 맞는 개발 환경

대상은 **ParaView 6.2.0 / Qt 6.9.0 / MSVC x64 Release**이다. runtime ZIP만으로는
`ParaView::pqComponents` 개발 파일을 얻을 수 없다. 다른 빌드의 DLL을 기존 stock
설치에 복사하거나 버전·artifact 검사를 완화하지 않는다.

기존 `scripts/fetch_post_native_windows.ps1`과 `build_post_native_windows.ps1`이 공식
고정 소스/Qt 입력, 기존 MSVC, 같은 Python으로 SDK와 runtime을 함께 빌드한다.
CI는 공개 저장소의 표준 `windows-2022`만 사용하며 artifact/cache 업로드는 없다.
[공식 무료 실행 조건](https://docs.github.com/en/billing/concepts/product-billing/github-actions)은
공개 저장소의 표준 runner에 적용된다. 새 실행은 root가 소스 게시 후 담당한다.

수동 실행의 `recover_runtime`을 선택하면 같은 SDK의 plugin load·기존 비교 저장과
재열기가 모두 성공한 뒤 실행 파일을 묶는다. 분할 파일은 미공개 draft release에만
보관하며 공개 출시하지 않는다. [실행 파일 회수](RUNTIME_RECOVERY_KO.md)의 라이선스·
검증·현지 사용 절차를 따른다. 이 단계는 Actions artifact/cache 저장소를 쓰지 않는다.

이전 진단 실행에서 실제 설치본의 Viskores DLL이 빠진 것을 확인했다.
공식 생성 `cmake_install.cmake`는 해당 DLL을 `Unspecified` 구성요소에 설치하지만,
기존 연결은 runtime/development/python만 설치했다. 같은 기존 target의 설치 스크립트만
새 prefix에 실행해 runtime은 DLL을 제외하고 Unspecified는 원 DLL과 같은 바이트를
설치함을 확인했다. root의 공통 교정이 이 구성요소를 추가한다. 이것은 같은 SDK의
필수 파일 설치 교정이며, 새 전체 runtime의 실제 loader 통과는 별도로 확인해야 한다.

## 기존 빌드 진입

일치하는 SDK가 준비된 x64 Native Tools PowerShell에서 기존 스크립트를 쓴다.
아래 경로 변수에는 각각 현재 SDK의 ParaView/Qt CMake 설정 폴더와 새 빌드 폴더를 넣는다.

```powershell
& $caePython scripts/native_check.py --timeout 300 --output-dir $checkOutput -- `
  $powerShell -NoProfile -File native/post_exit/Build-PostExit.ps1 `
  -ParaViewDir $paraViewCMake -Qt6Dir $qtCMake -BuildDir $newBuild -Python $caePython
```

기존 빌드·원 실패 로그를 덮어쓰지 않는다. 기본 스크립트는 transaction/C ABI를
확인하며, `-RunQtHarness`는 실제 Qt 창의 확인까지 수행한다. OS 활성화가 제한된
환경에서는 키보드 경로의 성공을 주장하지 않고 가능한 전용 Qt 함수만 실행한다.
컴파일/Qt harness와 실제 ParaView plugin 설치는 다른 확인이다.

## 실행기와 관리 저장 연결

기존 `scripts/post_exit_artifact.py`가 같은 SDK/runtime 관계·DLL 바이트를 manifest로
고정한다. `apps.desktop_post.native_exit.install`은 다음 환경을 사용해 공식
`LoadPlugin`으로 설치하고 같은 GUI thread·PID·주 창에 C ABI를 등록한다.

```powershell
$env:CAE_POST_EXIT_PLUGIN = $verifiedPlugin
$env:CAE_POST_PARAVIEW_ROOT = $matchingRuntime
```

이 환경은 전용 실행 프로세스 안에서만 지정하고, 작업 후 원래 값을 복원한다.
관리 Post 실행기는 같은 서비스·프로젝트를 유지하며 선택한 실행 파일도 해당
runtime의 `bin/paraview.exe`여야 한다. 기존 launcher는 환경을 상속한다. 설치된
artifact를 기본 실행기에 지정하는 접점과 정확한 실행 파일 일치 검증은 root의
공통 통합 범위다. 본 plugin은 임의 창 이름으로 사용자의 창을 제어하지 않는다.

기존 `scripts/post_native_exit_check.py`는 전용 scratch 프로젝트와 원 service를
사용해 실제 ParaView를 소유 Job에서 실행한다. `--route file-exit` 등의 선언만으로
메뉴나 키보드를 조작했다고 판정하지 않는다. 정상/취소/저장 실패/불확실 응답/
바쁜 저장/창 재진입에서 문서·원 결과가 유지되고, 저장 성공 뒤 한 번 종료되는지
직접 확인해야 한다. 확인용 앱·서비스는 성공·실패·timeout 모두 정확한 소유
프로세스만 정리한다.

현재 로컬 확인은 정확 Qt 6.9.0의 transaction·ABI·종료 event harness와 한국어
저장/취소/오류 창이다. 일치하는 완성 SDK/plugin DLL의 실제 load, ParaView File → Exit,
직접 OS 키 입력과 종료 후 새 ParaView 재열기는 아직 완료로 기록하지 않는다.
