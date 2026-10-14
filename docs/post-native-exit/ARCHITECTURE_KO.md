# 공식 경로 확인과 구현 경계

## 정확한 v6.2.0 공개 소스에서 확인한 사항

1. `Qt/ApplicationComponents/pqParaViewMenuBuilders.cxx`는 actionFileExit.triggered를
   QApplication.closeAllWindows에 연결한다. 같은 디렉터리 Resources/UI의
   pqFileMenuBuilder.ui는 actionFileExit의 shortcut을 Ctrl+Q로 정의한다.
2. `Clients/ParaView/ParaViewMainWindow.cxx`의 closeEvent는
   pqApplicationCore.getMainWindowEventManager().closeEvent(event)를 호출한다.
3. `Qt/Core/pqMainWindowEventManager.cxx`는 close(QCloseEvent*)를 동기 emit한다.
   `Qt/ApplicationComponents/pqMainWindowEventBehavior.cxx`의 stock handler는
   선택적 ShowSaveStateOnExit 설정에 따라 Save State 질문을 내고 Cancel이면 ignore한다.
4. Qt QObject event filter는 QWidget::close가 전달하는 QCloseEvent를 ignore하고
   전달을 막을 수 있다. 같은 QObject thread 제약을 지켜야 한다.
5. ParaView의 공식 autostart/UI_INTERFACES/paraview_add_plugin 경로가 있다.
   autostart.shutdown 및 Qt aboutToQuit는 이미 진행된 종료의 통지이지 저장 취소 API가 아니다.
6. `vtkPVSession::GetPendingProgress`, `pqProgressManager::isLocked/enableProgress`를
   사용한다. 별도 solver 상태를 만들거나 Abort 성공을 꾸미지 않는다.
7. `Qt/Components/pqPropertiesPanel.h`는 source/display/view Properties panel과
   canApply/canReset을 제공한다. QLineEdit의 editingFinished는 validator의
   Acceptable 조건을 요구하므로 SM unchecked property만으로 미완성 문자열을
   모두 알 수 있다고 가정하지 않았다.

공개 원본은 웹 도구로 읽었다. 원본 소스 전체를 이 인도물에서 빌드했다는 뜻은 아니다.
URL은 하단 SOURCE_REFERENCES.md에 고정된 태그 경로로 기록했다.

## 구현

CloseGate는 정확한 stock ParaViewMainWindow 한 개에만 설치한다. BEGIN은 기존
Controls.close_decision을 호출한다. literal allow만 통과시키고 예외/이상 정수/
Python None/bool/unknown은 block 처리한다. 검증된 허용은 한 번의 attempt에만 유효하다.

첫 event filter 이후 원 stock handler를 그대로 실행한다. 그 후 official close
signal에서 VALIDATE를 호출하여 동일 session, 전체 snapshot, saved receipt,
unchecked 실제 값/mtime, scoped Properties editor text fingerprint, busy를 재확인한다.
진행 계산 중에는 Qt progress filter가 입력을 막은 모달 오류 창에서 교착하지 않도록
오류 안내를 native status bar와 로그에 표시하고 즉시 close를 차단한다.
Save State 질문을 프로젝트 Save로 바꾸지 않고 다른 handler의 ignore를 accept로
덮어쓰지 않는다. 신호는 direct connection이며 stack QCloseEvent를 queued slot에 넘기지 않는다.

전용 settle timer는 original handler의 최종 veto가 남긴 허용을 폐기한다. 원 handler가
modal loop/processEvents에 있는 동안 AwaitingReview는 그대로 유지한다. timer는
동작할 때만 활성이고, 실제 close/abort/detach 때 정지한다. modal 동안 transport는
기존 실제 heartbeat만 보내며 queued mutation과 Ctrl+S 재진입을 실행하지 않는다.

실제 허용된 비spontaneous Hide를 받으면 CLOSED를 보낸다. Python은 기존
GuiDispatch.close로 broker receipt, pending queue, owner save registration,
interactor timer와 source observers를 정리한다. Native registration 해제는 그 전에
수행한다. 대화 취소/저장 실패 때는 이 정리를 수행하지 않는다.

C ABI는 96-byte status, 80-byte draft, 고정폭 uint64 식별자, int32 결정,
길이 제한 UTF-8만 전달한다. QObject/VTK 주소, 클래스 내부 offset, Qt mangled symbol,
C++ vtable은 Python에 노출하거나 패치하지 않는다. Python 바인딩용 SDK도 요구하지
않는다. **ParaView C++ GUI plugin 자체는 정확한 ParaView/Qt C++ SDK가 여전히 필요하다.**

native Properties fingerprint는 root panel의 실제 편집기 텍스트를 읽기만 하고
focus/자동 보정/apply/reset은 호출하지 않는다. C++ 내부 객체 identity까지 hash하므로
다른 편집기를 같은 텍스트로 재생성해도 동등 입력으로 조용히 인정하지 않는다.
Python에는 텍스트/주소 대신 digest와 pending만 전달한다. script editor는 범위 밖이다.
custom 비표준 Properties UI 또는 panel을 찾지 못한 경우는 UNKNOWN이다.

DLL handle과 CFUNCTYPE trampoline은 프로세스 단위로 보존하지만 owner 등록은 weakref
registry에서 제거한다. detach 실패 시 살아 있는 native callback을 해제했다고
꾸미지 않고 보존한다. 반복 열기는 새 monotonic registration과 owner session으로
등록한다. atexit는 마지막 callable 정리일 뿐 저장 관문이 아니다.

## 알려진 native 검증 경계

현재 코드는 exact stock v6.2.0용이다. 임의의 다른 plugin이 이후에 close handler를
추가하거나 별도 QApplication::exit/강제 파괴를 실행하는 경우까지 veto를 보장하지
않는다. OS 강제 종료, process kill, crash는 저장 취소로 막을 수 없다.

원 v6.2.0 pqMainWindowEventManager는 close 신호 전에 Closing=true를 쓰고 public reset을
제공하지 않는다. 이 plugin의 취소/실패/UNKNOWN은 그 앞에서 차단되므로 해당 경로에는
진입하지 않는다. 선택적으로 켠 stock Save State 질문이나 뒤 handler가 나중에
취소한 경우 Closing flag의 upstream 동작은 남는다. 내부 flag를 ABI 조작으로 고치지
않았다. owner/registration 재시도는 유지하지만 해당 설정을 포함한 실제 ParaView
재시도 및 다른 stock 기능 영향은 Windows 수용 검사에서 확인해야 한다.

현재 독립 프로젝트 저장/분석 복구/PNG export 구현은 변경하지 않았다. 실제 저장 후
새 프로세스에서 field/time/view/원분석 보존을 증명하는 것은 native acceptance의
남은 항목이며 fake owner 단위검사로 대체하지 않는다.
