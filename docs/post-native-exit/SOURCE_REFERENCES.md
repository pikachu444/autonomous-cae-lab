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
- Qt open source/obligations:
  https://www.qt.io/development/download-open-source
  https://www.qt.io/development/open-source-lgpl-obligations
- MS Build Tools OSS use:
  https://devblogs.microsoft.com/cppblog/updates-to-visual-studio-build-tools-license-for-c-and-cpp-open-source-projects/

Web source 검토와 full upstream checkout/Windows compilation은 별개다. 본 작업에서
실제 완료한 local 실행/실패 로그는 evidence에만 기록하며 source 링크로 대체하지 않는다.
