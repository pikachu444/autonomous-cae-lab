/* SPDX-License-Identifier: BSD-3-Clause */
#include "CloseGate.h"
#include <QApplication>
#include <QMainWindow>
#include <QStatusBar>
#include <QDebug>
#include <QCloseEvent>
#include <QMessageBox>
#include <QPushButton>
#include <QThread>
#include <QHideEvent>
#include <QScopedValueRollback>
#include <utility>
namespace cae {
CloseGate::CloseGate(std::function<uint32_t()> nativeBusy, QObject* parent)
  : QObject(parent), NativeBusy(std::move(nativeBusy)), Settle(this) {
  Settle.setSingleShot(true);
  connect(&Settle, &QTimer::timeout, this, [this]() { settle(); });
}
CloseGate::~CloseGate() { clear(); }
int CloseGate::attach(QWidget* main, uint64_t registration, uint64_t client, cae_exit_callback callback) {
  if (QThread::currentThread() != thread()) return CAE_WRONG_THREAD;
  if (Registration || DialogOpen) return CAE_BUSY;
  if (!main || main->thread() != thread() || !registration || !client || !callback) return CAE_BAD_ARGUMENT;
  Main = main; Window = static_cast<uint64_t>(main->winId());
  Registration = registration; Client = client; Callback = callback;
  Main->installEventFilter(this);
  Connections.push_back(connect(main, &QObject::destroyed, this, [this]() {
    // This is cleanup of an already destroyed object, never an exit veto.
    notify(CAE_DESTROYED);
    clear();
  }, Qt::DirectConnection));
  Connections.push_back(connect(qApp, &QCoreApplication::aboutToQuit, this, [this]() { shutdown(); },
                                Qt::DirectConnection));
  return CAE_OK;
}
void CloseGate::clear() {
  Settle.stop();
  if (Main) Main->removeEventFilter(this);
  for (const auto& connection : Connections) disconnect(connection);
  Connections.clear();
  Main.clear(); Registration = Client = Window = 0; Callback = nullptr;
  Transaction.abort(); LastDecision = CAE_UNKNOWN;
}
int CloseGate::detach(uint64_t registration) {
  if (QThread::currentThread() != thread()) return CAE_WRONG_THREAD;
  if (!registration || registration != Registration) return CAE_WRONG_OWNER;
  // Do not unload the Python platform while a native modal dialog is using it.
  if (DialogOpen) return CAE_BUSY;
  clear();
  return CAE_OK;
}
int CloseGate::notify(uint32_t event) {
  if (!Callback || !Registration || QThread::currentThread() != thread()) return CAE_UNKNOWN;
  auto callback = Callback;
  const auto result = callback(Client, Registration, Transaction.attempt(), event);
  return result == CAE_ALLOW ? CAE_ALLOW : (result == CAE_BLOCK ? CAE_BLOCK : CAE_UNKNOWN);
}
void CloseGate::abort() {
  if (!Transaction.active()) return;
  notify(CAE_ABORTED);
  Transaction.abort();
  Settle.stop();
}
bool CloseGate::eventFilter(QObject* watched, QEvent* event) {
  if (!Registration || watched != Main.data()) return false;
  if (event->type() == QEvent::Close) {
    auto close = static_cast<QCloseEvent*>(event);
    if (DialogOpen || !Transaction.begin()) { close->ignore(); return true; }
    const auto registration = Registration;
    LoopLevel = QThread::currentThread()->loopLevel();
    // Query also inside Python's shared gate, where it can display a safe error.
    LastDecision = notify(CAE_BEGIN);
    if (Registration != registration || !Transaction.decide(LastDecision)) {
      close->ignore(); return true;
    }
    // Returning false preserves stock closeEvent/Save State/editor semantics.
    // A later ignore must not destroy the Owner. Timer waits out nested loops.
    Settle.start(0);
    return false;
  }
  if (event->type() == QEvent::Hide && !event->spontaneous() && Transaction.reviewed() &&
      !InCloseNotification) {
    QScopedValueRollback<bool> notifying(InCloseNotification, true);
    Settle.stop();
    LastDecision = notify(CAE_CLOSED);
    // Normal callback uses GuiDispatch.close -> exact detach. Do not silently
    // claim cleanup succeeded when the callback failed.
    if (Registration && LastDecision == CAE_ALLOW) clear();
  }
  return false;
}
void CloseGate::reviewClose(QCloseEvent* event) {
  if (!Registration || !event || Transaction.phase() != CloseTransaction::Phase::AwaitingReview) return;
  if (!event->isAccepted()) { abort(); return; }
  const auto registration = Registration;
  LastDecision = notify(CAE_VALIDATE);
  if (Registration != registration) { event->ignore(); return; }
  // Never accept a QCloseEvent ignored by an earlier official stock handler.
  if (LastDecision != CAE_ALLOW || !event->isAccepted()) {
    event->ignore(); abort(); return;
  }
  Transaction.review(true, LastDecision);
}
void CloseGate::settle() {
  if (!Registration || !Transaction.active()) return;
  if (Transaction.phase() == CloseTransaction::Phase::AwaitingReview ||
      QThread::currentThread()->loopLevel() > LoopLevel) { Settle.start(10); return; }
  // No nonspontaneous Hide was observed: stock/downstream code vetoed, or no
  // official review was emitted. Invalidate the lease; the next request asks anew.
  abort();
}
void CloseGate::shutdown() {
  if (!Registration) return;
  notify(CAE_SHUTDOWN);
  clear();
}
int CloseGate::prompt(uint64_t registration) {
  if (QThread::currentThread() != thread() || registration != Registration || !Main || DialogOpen)
    return 3;
  QScopedValueRollback<bool> dialog(DialogOpen, true);
  QMessageBox box(Main);
  box.setObjectName("caePostProjectCloseDialog");
  box.setWindowTitle(QString::fromUtf8("프로젝트를 저장하고 닫으시겠습니까?"));
  box.setIcon(QMessageBox::Question);
  box.setTextFormat(Qt::PlainText);
  box.setText(QString::fromUtf8("후처리 프로젝트에 저장하지 않은 변경이 있습니다."));
  box.setInformativeText(QString::fromUtf8("저장은 원본 연결과 현재 뷰를 프로젝트에 보존합니다.\n"
    "적용하지 않은 Properties는 먼저 적용하거나 되돌려야 저장할 수 있습니다."));
  auto save = box.addButton(QString::fromUtf8("저장"), QMessageBox::AcceptRole);
  auto discard = box.addButton(QString::fromUtf8("저장 안 함"), QMessageBox::DestructiveRole);
  auto cancel = box.addButton(QString::fromUtf8("취소"), QMessageBox::RejectRole);
  save->setObjectName("caePostSave"); discard->setObjectName("caePostDiscard"); cancel->setObjectName("caePostCancel");
  for (auto button : {save, discard, cancel}) button->setMinimumSize(88, 32);
  box.setDefaultButton(cancel); box.setEscapeButton(cancel);
  box.setWindowModality(Qt::WindowModal);
  box.exec();
  if (box.clickedButton() == save) return 1;
  if (box.clickedButton() == discard) return 2;
  return 3;
}
int CloseGate::error(uint64_t registration, const QString& message) {
  if (QThread::currentThread() != thread()) return CAE_WRONG_THREAD;
  if (registration != Registration || !Main) return CAE_WRONG_OWNER;
  if (DialogOpen) return CAE_BUSY;
  // pqProgressManager can consume Qt mouse/key events during a native job.
  // A modal acknowledgement here could suspend the job inside processEvents
  // while its own progress filter makes the acknowledgement impossible.
  if (!NativeBusy || NativeBusy() != 0) {
    if (auto window = qobject_cast<QMainWindow*>(Main.data())) window->statusBar()->showMessage(message);
    qWarning().noquote() << message;
    return CAE_OK;
  }
  QScopedValueRollback<bool> dialog(DialogOpen, true);
  QMessageBox box(Main);
  box.setObjectName("caePostProjectCloseError");
  box.setWindowTitle(QString::fromUtf8("현재 창을 유지합니다"));
  box.setIcon(QMessageBox::Warning); box.setTextFormat(Qt::PlainText); box.setText(message);
  auto button = box.addButton(QString::fromUtf8("확인"), QMessageBox::AcceptRole);
  button->setObjectName("caePostErrorAcknowledge"); button->setMinimumSize(88, 32);
  box.setDefaultButton(button); box.setEscapeButton(button); box.exec();
  return CAE_OK;
}
void CloseGate::status(cae_exit_status& output) const {
  output.registration = Registration; output.client = Client; output.window = Window;
  output.attempt = Transaction.attempt(); output.installed = Registration ? 1 : 0;
  output.in_action = actionInProgress() ? 1 : 0;
  output.native_busy = NativeBusy ? NativeBusy() : 2;
  output.settle_timer = Settle.isActive() ? 1 : 0; output.filter_count = Registration ? 1 : 0;
  output.last_decision = LastDecision;
  output.observer_count = static_cast<uint32_t>(Connections.size());
}
}
