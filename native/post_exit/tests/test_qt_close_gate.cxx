/* SPDX-License-Identifier: BSD-3-Clause */
#include "CloseGate.h"
#include "NativeDraft.h"
#include <QLineEdit>
#include <QDoubleValidator>
#include <QAction>
#include <QApplication>
#include <QCloseEvent>
#include <QMainWindow>
#include <QStatusBar>
#include <QMenuBar>
#include <QMessageBox>
#include <QPushButton>
#include <QTest>
#include <QTimer>
#include <QThread>
#include <QSignalSpy>
#include <functional>
#include <algorithm>
#include <QEventLoop>
#include <vector>
#ifdef Q_OS_WIN
#include <windows.h>
#endif
namespace {
struct Answers {
  int begin = CAE_BLOCK, validate = CAE_ALLOW;
  std::function<int()> onBegin;
  std::vector<uint32_t> events;
};
Answers* answers = nullptr;
int32_t CAE_EXIT_CALL callback(uint64_t, uint64_t, uint64_t, uint32_t event) {
  answers->events.push_back(event);
  if (event == CAE_BEGIN) return answers->onBegin ? answers->onBegin() : answers->begin;
  return event == CAE_VALIDATE ? answers->validate : CAE_ALLOW;
}
class Window : public QMainWindow {
public:
  cae::CloseGate* gate = nullptr;
  bool stockVeto = false, lateVeto = false;
  int stockCalls = 0;
  std::function<void()> stockModal;
  std::function<void()> afterReview;
protected:
  void closeEvent(QCloseEvent* event) override {
    ++stockCalls;
    if (stockModal) stockModal();
    if (stockVeto) event->ignore();
    if (gate) gate->reviewClose(event);
    if (afterReview) afterReview();
    if (lateVeto) event->ignore();
  }
};
class DownstreamVeto : public QObject {
protected:
  bool eventFilter(QObject*, QEvent* event) override {
    if (event->type() != QEvent::Close) return false;
    static_cast<QCloseEvent*>(event)->ignore();
    return true;
  }
};
}
class QtCloseTest : public QObject {
  Q_OBJECT
private Q_SLOTS:
  void initTestCase() { QApplication::setQuitOnLastWindowClosed(false); }
  void fileExitActionUsesOriginalCloseEventOnce() {
    Answers a; answers = &a;
    Window main; cae::CloseGate gate([](){ return 0u; }); main.gate = &gate;
    QCOMPARE(gate.attach(&main, 42, 42, callback), CAE_OK);
    auto file = main.menuBar()->addMenu(QString::fromUtf8("파일"));
    auto exit = file->addAction(QString::fromUtf8("종료"));
    exit->setObjectName("actionFileExit");
    connect(exit, &QAction::triggered, qApp, &QApplication::closeAllWindows);
    main.show();
    exit->trigger();
    QVERIFY(main.isVisible()); QCOMPARE(main.stockCalls, 0);
    a.begin = CAE_ALLOW;
    exit->trigger();
    QVERIFY(!main.isVisible()); QCOMPARE(main.stockCalls, 1);
    QCOMPARE(std::count(a.events.begin(), a.events.end(), CAE_BEGIN), 2);
    QCOMPARE(std::count(a.events.begin(), a.events.end(), CAE_VALIDATE), 1);
    QCOMPARE(std::count(a.events.begin(), a.events.end(), CAE_CLOSED), 1);
    QCOMPARE(gate.registration(), uint64_t(0));
  }
  void actionsAndKeyboard() {
    Answers a; answers = &a;
    Window window;
    cae::CloseGate gate([]() { return 0u; }); window.gate = &gate;
    QCOMPARE(gate.attach(&window, 1, 1, callback), CAE_OK);
    auto action = new QAction("Exit", &window); action->setObjectName("actionFileExit");
    action->setShortcut(QKeySequence("Ctrl+Q")); window.addAction(action);
    connect(action, &QAction::triggered, qApp, &QApplication::closeAllWindows);
    window.show(); QVERIFY(QTest::qWaitForWindowExposed(&window));
    action->trigger(); QVERIFY(window.isVisible()); QCOMPARE(window.stockCalls, 0);
    window.activateWindow(); QVERIFY(QTest::qWaitForWindowActive(&window)); window.setFocus();
    QTest::keyClick(&window, Qt::Key_Q, Qt::ControlModifier);
    QTRY_COMPARE(static_cast<int>(a.events.size()), 2);
    QVERIFY(window.isVisible());
    a.begin = CAE_ALLOW;
    action->trigger(); QVERIFY(!window.isVisible());
    QCOMPARE(a.events[a.events.size()-2], uint32_t(CAE_VALIDATE));
    QCOMPARE(a.events.back(), uint32_t(CAE_CLOSED));
    QCOMPARE(gate.registration(), uint64_t(0));
  }
  void nativeWindowsClosePaths() {
#ifndef Q_OS_WIN
    QSKIP("Windows SC_CLOSE/Alt+F4 test only; not emulated on other platforms");
#else
    Answers a; answers = &a;
    Window window; cae::CloseGate gate([](){ return 0u; }); window.gate = &gate;
    QCOMPARE(gate.attach(&window, 2, 2, callback), CAE_OK);
    window.show(); QVERIFY(QTest::qWaitForWindowExposed(&window));
    SendMessageW(reinterpret_cast<HWND>(window.winId()), WM_SYSCOMMAND, SC_CLOSE, 0);
    QTRY_COMPARE(a.events.size(), size_t(1)); QVERIFY(window.isVisible());
    window.activateWindow(); QVERIFY(QTest::qWaitForWindowActive(&window)); window.setFocus();
    // QWidget QTest keyClick dispatches a QKeyEvent directly; it bypasses
    // Windows' default system-key handling of Alt+F4. Target only this owned
    // HWND, exercising the system-key message path without global input.
    const auto hwnd = reinterpret_cast<HWND>(window.winId());
    DWORD windowProcess = 0;
    GetWindowThreadProcessId(hwnd, &windowProcess);
    QCOMPARE(windowProcess, GetCurrentProcessId());
    BYTE previousKeys[256], systemKeys[256];
    QVERIFY(GetKeyboardState(previousKeys));
    std::copy(std::begin(previousKeys), std::end(previousKeys), std::begin(systemKeys));
    // Qt's Windows mapper reads the current UI thread's keyboard state, not
    // just the message's Alt context bit. SetKeyboardState is thread-local;
    // restore it before processing any asynchronously posted close event.
    systemKeys[VK_MENU] |= 0x80;
    systemKeys[VK_LMENU] |= 0x80;
    QVERIFY(SetKeyboardState(systemKeys));
    SendMessageW(hwnd, WM_SYSKEYDOWN, VK_F4, LPARAM(1) | (LPARAM(1) << 29));
    SendMessageW(hwnd, WM_SYSKEYUP, VK_F4,
                 LPARAM(1) | (LPARAM(1) << 29) | (LPARAM(1) << 30) | (LPARAM(1) << 31));
    QVERIFY(SetKeyboardState(previousKeys));
    QTRY_COMPARE(a.events.size(), size_t(2));
    QVERIFY(window.isVisible());
#endif
  }
  void allUnknownsAndRetry() {
    Answers a; answers = &a;
    Window window; cae::CloseGate gate([](){ return 0u; }); window.gate = &gate;
    QCOMPARE(gate.attach(&window, 3, 3, callback), CAE_OK);
    window.show();
    for (int decision : std::initializer_list<int>{CAE_BLOCK, CAE_UNKNOWN, 2, -6}) {
      a.begin = decision; QVERIFY(!window.close()); QVERIFY(window.isVisible());
    }
    a.begin = CAE_ALLOW; a.validate = CAE_UNKNOWN;
    QVERIFY(!window.close()); QVERIFY(window.isVisible());
    QCOMPARE(a.events.back(), uint32_t(CAE_ABORTED));
    a.validate = CAE_ALLOW;
    QVERIFY(window.close()); QVERIFY(!window.isVisible());
  }
  void stockAndLateVetoReleaseLeaseNotOwner() {
    Answers a; answers = &a; a.begin = CAE_ALLOW;
    Window window; cae::CloseGate gate([](){ return 0u; }); window.gate = &gate;
    QCOMPARE(gate.attach(&window, 4, 4, callback), CAE_OK);
    window.show(); window.stockVeto = true;
    QVERIFY(!window.close()); QCOMPARE(a.events.back(), uint32_t(CAE_ABORTED));
    window.stockVeto = false; window.lateVeto = true;
    QVERIFY(!window.close()); QVERIFY(gate.actionInProgress());
    QTRY_VERIFY(!gate.actionInProgress());
    QCOMPARE(a.events.back(), uint32_t(CAE_ABORTED));
    QCOMPARE(gate.registration(), uint64_t(4));
    window.lateVeto = false; QVERIFY(window.close());
  }
  void nativeModalKeepsLeaseAndDoesNotAskTwice() {
    Answers a; answers = &a; a.begin = CAE_ALLOW;
    Window window; cae::CloseGate gate([](){ return 0u; }); window.gate = &gate;
    QCOMPARE(gate.attach(&window, 5, 5, callback), CAE_OK);
    window.show();
    window.stockModal = [&]() {
      QEventLoop modal;
      QTimer::singleShot(30, &modal, [&]() {
        const bool active = gate.actionInProgress();
        modal.quit();
        QVERIFY(active);
      });
      modal.exec();
    };
    QVERIFY(window.close());
    QCOMPARE(std::count(a.events.begin(), a.events.end(), CAE_BEGIN), 1);
    QVERIFY(std::find(a.events.begin(), a.events.end(), CAE_ABORTED) == a.events.end());
  }
  void filteredCloseWithoutOfficialReviewReleasesLease() {
    Answers a; answers = &a; a.begin = CAE_ALLOW;
    Window window; DownstreamVeto veto;
    // Qt calls the most recently installed filter first. The other filter
    // rejects after our BEGIN, so the stock closeEvent/review is never reached.
    window.installEventFilter(&veto);
    cae::CloseGate gate([](){ return 0u; }); window.gate = &gate;
    QCOMPARE(gate.attach(&window, 7, 7, callback), CAE_OK);
    window.show();
    QVERIFY(!window.close()); QVERIFY(window.isVisible());
    QCOMPARE(window.stockCalls, 0);
    QVERIFY(gate.actionInProgress());
    QTRY_VERIFY(!gate.actionInProgress());
    QCOMPARE(a.events.back(), uint32_t(CAE_ABORTED));
    QCOMPARE(gate.registration(), uint64_t(7));
    QVERIFY(std::find(a.events.begin(), a.events.end(), CAE_CLOSED) == a.events.end());
    window.removeEventFilter(&veto);
    QVERIFY(window.close());
    QCOMPARE(window.stockCalls, 1);
    QCOMPARE(a.events.back(), uint32_t(CAE_CLOSED));
    QCOMPARE(gate.registration(), uint64_t(0));
  }
  void stockProcessEventsDoesNotExpirePermission() {
    for (const bool reviewed : {false, true}) {
      Answers a; answers = &a; a.begin = CAE_ALLOW;
      Window window; cae::CloseGate gate([](){ return 0u; }); window.gate = &gate;
      QCOMPARE(gate.attach(&window, 8, 8, callback), CAE_OK);
      window.show();
      auto processEvents = [&]() {
        QCoreApplication::processEvents();
        QVERIFY(gate.actionInProgress());
        QVERIFY(std::find(a.events.begin(), a.events.end(), CAE_ABORTED) == a.events.end());
      };
      if (reviewed) window.afterReview = processEvents;
      else window.stockModal = processEvents;
      QVERIFY(window.close());
      QCOMPARE(a.events.back(), uint32_t(CAE_CLOSED));
      QCOMPARE(gate.registration(), uint64_t(0));
    }
  }
  void scopedEditorAndUnmanagedWindow() {
    Answers a; answers = &a;
    Window main, unmanaged;
    QMainWindow editor(&main, Qt::Window);
    cae::CloseGate gate([](){ return 0u; }); main.gate = &gate;
    QCOMPARE(gate.attach(&main, 6, 6, callback), CAE_OK);
    main.show(); editor.show(); unmanaged.show();
    QVERIFY(editor.close()); QVERIFY(unmanaged.close()); QVERIFY(a.events.empty());
    QVERIFY(!main.close()); QCOMPARE(a.events.size(), size_t(1));
  }
  void threeAttachDetachCycles() {
    Answers a; answers = &a;
    Window main; main.show(); cae::CloseGate gate([](){ return 0u; }); main.gate = &gate;
    for (uint64_t id = 10; id != 13; ++id) {
      QCOMPARE(gate.attach(&main, id, id, callback), CAE_OK);
      QVERIFY(!main.close());
      QCOMPARE(gate.detach(id), CAE_OK);
      cae_exit_status status{}; gate.status(status);
      QCOMPARE(status.installed, 0u); QCOMPARE(status.filter_count, 0u); QCOMPARE(status.settle_timer, 0u);
      QCOMPARE(status.observer_count, 0u);
    }
    QCOMPARE(a.events.size(), size_t(3));
  }
  void progressWarningDoesNotEnterAnUnclickableModalDialog() {
    Answers a; answers = &a;
    Window main; main.show(); cae::CloseGate gate([](){ return 1u; }); main.gate = &gate;
    QCOMPARE(gate.attach(&main, 30, 30, callback), CAE_OK);
    const auto message = QString::fromUtf8("현재 작업이 끝난 뒤 창을 닫으세요.");
    QCOMPARE(gate.error(30, message), CAE_OK);
    QCOMPARE(main.statusBar()->currentMessage(), message);
    QVERIFY(main.findChildren<QMessageBox*>().empty());
  }
  void rawInvalidDraftIsReadOnlyAndScoped() {
    QWidget panel, unrelated;
    QLineEdit edit(&panel), other(&unrelated);
    QDoubleValidator validator;
    edit.setValidator(&validator); edit.setText("1e"); edit.setModified(true);
    auto first = cae::captureDraft({&panel}, false);
    QCOMPARE(first.unapplied, 1u); QCOMPARE(edit.text(), QString("1e"));
    other.setText("not a Properties editor");
    auto unchanged = cae::captureDraft({&panel}, false);
    QCOMPARE(QByteArray(first.digest, 64), QByteArray(unchanged.digest, 64));
    edit.setText("1e2"); edit.setModified(true);
    auto changed = cae::captureDraft({&panel}, false);
    QCOMPARE(changed.unapplied, 0u);
    QVERIFY(QByteArray(first.digest, 64) != QByteArray(changed.digest, 64));
  }
  void koreanDialogHasExplicitCancelDefaultAndCapture() {
    Answers a; answers = &a;
    Window main; main.resize(640, 420); main.show();
    cae::CloseGate gate([](){ return 0u; }); main.gate = &gate;
    QCOMPARE(gate.attach(&main, 20, 20, callback), CAE_OK);
    for (const auto width : {1100, 640}) {
      main.resize(width, 480);
      QTimer::singleShot(20, &main, [&]() {
        auto box = main.findChild<QMessageBox*>("caePostProjectCloseDialog"); QVERIFY(box);
        auto cancel = box->findChild<QPushButton*>("caePostCancel"); QVERIFY(cancel);
        QCOMPARE(cancel->text(), QString::fromUtf8("취소"));
        QCOMPARE(box->defaultButton(), cancel); QCOMPARE(box->escapeButton(), cancel);
        const auto folder = qEnvironmentVariable("CAE_EXIT_CAPTURE_DIR");
        if (!folder.isEmpty()) QVERIFY(box->grab().save(folder + QString("/qt-dialog-%1.png").arg(width)));
        cancel->click();
      });
      QCOMPARE(gate.prompt(20), 3);
    }
  }
  void explicitPromptChoicesBlockReentrantClose() {
    Answers a; answers = &a;
    Window main; main.show();
    cae::CloseGate gate([](){ return 0u; }); main.gate = &gate;
    QCOMPARE(gate.attach(&main, 40, 40, callback), CAE_OK);
    const char* choices[] = {"caePostSave", "caePostDiscard", "caePostCancel"};
    for (int i = 0; i < 3; ++i) {
      bool checked = false;
      QTimer::singleShot(20, &main, [&]() {
        auto box = main.findChild<QMessageBox*>("caePostProjectCloseDialog");
        if (!box) { return; }
        auto button = box->findChild<QPushButton*>(choices[i]);
        const bool stayed = !main.close() && main.isVisible() && gate.registration() == 40;
        checked = stayed && button && a.events.empty();
        if (button) button->click(); else box->reject();
      });
      QCOMPARE(gate.prompt(40), i + 1);
      QVERIFY(checked); QVERIFY(main.isVisible());
    }
    QCOMPARE(gate.detach(40), CAE_OK);
  }
  void errorAcknowledgementPreservesDraftAndOwner() {
    Answers a; answers = &a;
    Window main; main.show(); QLineEdit draft(&main); draft.setText("1e");
    cae::CloseGate gate([](){ return 0u; }); main.gate = &gate;
    QCOMPARE(gate.attach(&main, 41, 41, callback), CAE_OK);
    bool checked = false;
    QTimer::singleShot(20, &main, [&]() {
      auto box = main.findChild<QMessageBox*>("caePostProjectCloseError");
      if (!box) { return; }
      auto acknowledge = box->findChild<QPushButton*>("caePostErrorAcknowledge");
      checked = !main.close() && main.isVisible() && draft.text() == "1e" &&
                gate.registration() == 41 && a.events.empty();
      const auto folder = qEnvironmentVariable("CAE_EXIT_CAPTURE_DIR");
      if (!folder.isEmpty()) checked = checked && box->grab().save(folder + "/qt-save-error.png");
      if (acknowledge) acknowledge->click(); else box->reject();
    });
    QCOMPARE(gate.error(41, QString::fromUtf8("프로젝트를 저장하지 못했습니다. 입력과 현재 결과를 유지합니다.")), CAE_OK);
    QVERIFY(checked); QCOMPARE(draft.text(), QString("1e"));
    QCOMPARE(gate.registration(), uint64_t(41));
    QCOMPARE(gate.detach(41), CAE_OK);
  }
};
int main(int argc, char** argv) {
  QApplication app(argc, argv);
  QtCloseTest test;
  // Model the real application: close dispatch starts inside its running
  // event loop. DeferredDelete before exec() has different Qt semantics.
  QTimer::singleShot(0, &test, [&]() { app.exit(QTest::qExec(&test, argc, argv)); });
  return app.exec();
}
#include "test_qt_close_gate.moc"
