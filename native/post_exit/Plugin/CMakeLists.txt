paraview_plugin_add_auto_start(
  CLASS_NAME pqCaePostExitStarter
  STARTUP onStartup SHUTDOWN onShutdown
  INTERFACES autostart_interfaces SOURCES autostart_sources)
paraview_add_plugin(CaePostExit
  REQUIRED_ON_CLIENT VERSION "1.0.0"
  UI_INTERFACES ${autostart_interfaces}
  SOURCES ${autostart_sources}
    pqCaePostExitStarter.h pqCaePostExitStarter.cxx
    CloseGate.h CloseGate.cxx NativeDraft.h NativeDraft.cxx CloseTransaction.h cae_post_exit_abi.h)
target_link_libraries(CaePostExit PRIVATE ParaView::pqComponents
  Qt6::Core Qt6::Gui Qt6::Widgets)
target_compile_definitions(CaePostExit PRIVATE CAE_POST_EXIT_BUILD)
target_compile_features(CaePostExit PRIVATE cxx_std_17)
if(MSVC)
  target_compile_options(CaePostExit PRIVATE /utf-8 /W4)
endif()
