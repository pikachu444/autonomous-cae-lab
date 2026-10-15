# 확인한 공식 출처

확인 기준: 요청에 지정된 ParaView v6.2.0, Qt 6.9.0/6.9 문서. 최신 general 문서는
license/build 정책 설명에만 사용하고 제품 API 판별은 정확한 태그 source로 확인했다.

- File > Exit 실제 연결:
  https://raw.githubusercontent.com/Kitware/ParaView/v6.2.0/Qt/ApplicationComponents/pqParaViewMenuBuilders.cxx
- QAction objectName/shortcut:
  https://raw.githubusercontent.com/Kitware/ParaView/v6.2.0/Qt/ApplicationComponents/Resources/UI/pqFileMenuBuilder.ui
- stock main closeEvent:
  https://raw.githubusercontent.com/Kitware/ParaView/v6.2.0/Clients/ParaView/ParaViewMainWindow.cxx
- close signal/Closing flag:
  https://raw.githubusercontent.com/Kitware/ParaView/v6.2.0/Qt/Core/pqMainWindowEventManager.cxx
- stock Save State/Cancel:
  https://raw.githubusercontent.com/Kitware/ParaView/v6.2.0/Qt/ApplicationComponents/pqMainWindowEventBehavior.cxx
- exact mainWidget API:
  https://raw.githubusercontent.com/Kitware/ParaView/v6.2.0/Qt/Core/pqCoreUtilities.h
- native pending progress:
  https://raw.githubusercontent.com/Kitware/ParaView/v6.2.0/Remoting/Core/vtkPVSession.h
  https://raw.githubusercontent.com/Kitware/ParaView/v6.2.0/Qt/Core/pqProgressManager.h
- native Properties panel:
  https://raw.githubusercontent.com/Kitware/ParaView/v6.2.0/Qt/Components/pqPropertiesPanel.h
- official GUI autostart plugin/CMake:
  https://raw.githubusercontent.com/Kitware/ParaView/v6.2.0/Examples/Plugins/Autostart/Plugin/CMakeLists.txt
  https://raw.githubusercontent.com/Kitware/ParaView/v6.2.0/Examples/Plugins/Autostart/CMakeLists.txt
  https://www.paraview.org/paraview-docs/latest/cxx/PluginHowto.html
- development install option:
  https://raw.githubusercontent.com/Kitware/ParaView/v6.2.0/CMake/ParaViewOptions.cmake
- Qt event filter/close contract:
  https://doc.qt.io/qt-6/qobject.html#installEventFilter
  https://doc.qt.io/qt-6/qcloseevent.html
  https://doc.qt.io/archives/qt-6.9/qlineedit.html
- Qt Windows source build:
  https://doc.qt.io/archives/qt-6.9/windows-building.html
- Qt 6.9.0 QWidget test keyboard dispatch / Windows Alt+F4 native modifier handling:
  https://github.com/qt/qtbase/blob/v6.9.0/src/testlib/qtestkeyboard.h
  https://github.com/qt/qtbase/blob/v6.9.0/src/plugins/platforms/windows/qwindowskeymapper.cpp
- 공개 Qt 6.9.0/MSVC2022 개발 archive와 ParaView exact CI hash:
  https://download.qt.io/online/qtsdkrepository/windows_x86/desktop/qt6_690/qt6_690/
  https://gitlab.kitware.com/paraview/paraview-superbuild/-/blob/v6.2.0/.gitlab/ci/download_qt6_hashes.cmake
- 정확 ParaView source release:
  https://www.paraview.org/files/v6.2/ParaView-v6.2.0.tar.xz
- 빌드 소스를 수정하지 않는 CMake project 설정 훅 / Windows thread keyboard state:
  https://cmake.org/cmake/help/v3.30/variable/CMAKE_PROJECT_INCLUDE.html
  https://learn.microsoft.com/en-us/windows/win32/api/winuser/nf-winuser-setkeyboardstate
- Qt open source/obligations:
  https://www.qt.io/development/download-open-source
  https://www.qt.io/development/open-source-lgpl-obligations
- MS Build Tools OSS use:
  https://devblogs.microsoft.com/cppblog/updates-to-visual-studio-build-tools-license-for-c-and-cpp-open-source-projects/
- MSVC linker/CRT 혼합 버전 및 LTCG 제한:
  https://learn.microsoft.com/en-us/cpp/porting/binary-compat-2015-2017?view=msvc-170
- 공개 standard Windows runner/compute, artifact 보관 및 release assets:
  https://docs.github.com/en/actions/reference/runners/github-hosted-runners
  https://docs.github.com/en/billing/concepts/product-billing/github-actions
  https://docs.github.com/en/repositories/releasing-projects-on-github/about-releases
- 공식 MSBuild 파일별 compiler scheduler:
  https://devblogs.microsoft.com/cppblog/cpp-build-throughput-investigation-and-tune-up/
  https://learn.microsoft.com/en-us/visualstudio/msbuild/multitooltask-task?view=visualstudio

Web source 검토와 full upstream checkout/Windows compilation은 별개다. 본 작업에서
실제 완료한 local 실행/실패 로그는 evidence에만 기록하며 source 링크로 대체하지 않는다.

## GitHub workflow의 실행 컨텍스트

- https://docs.github.com/en/actions/reference/workflows-and-actions/contexts#context-availability — job-level env는 runner context를 지원하지 않는다. RUNNER_TEMP는 실행 중인 step에서 읽는다.
- https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-commands#setting-an-environment-variable — POST_NATIVE_ROOT를 GITHUB_ENV에 기록해 후속 step에 전달한다. 초기화 실패 시 영수증 출력은 건너뛰며 원 실패를 보존한다.
- https://cmake.org/cmake/help/v3.31/manual/cmake.1.html#run-a-command-line-tool — 기존 필수 도구의 `-E tar`는 LZMA/7zip을 지원한다. `-E chdir`로 소유한 출력 경로에 추출하며 호출자의 작업 폴더를 바꾸지 않는다.
