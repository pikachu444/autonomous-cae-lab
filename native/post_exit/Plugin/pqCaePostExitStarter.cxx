/* SPDX-License-Identifier: BSD-3-Clause */
#include "pqCaePostExitStarter.h"
#include "CloseGate.h"
#include "NativeDraft.h"
#include <pqPropertiesPanel.h>
#include <QApplication>
#include <QCloseEvent>
#include <QMainWindow>
#include <QThread>
#include <QString>
#include <QByteArray>
#include <pqApplicationCore.h>
#include <pqCoreUtilities.h>
#include <pqMainWindowEventManager.h>
#include <pqProgressManager.h>
#include <pqServer.h>
#include <pqServerManagerModel.h>
#include <vtkSMSession.h>
#include <limits>
#include <cstring>
namespace {
QWidget* exactMainWindow() {
  if (!qApp || QThread::currentThread() != qApp->thread()) return nullptr;
  QWidget* selected = pqCoreUtilities::mainWidget();
  if (!selected || !selected->isWindow() || !selected->inherits("ParaViewMainWindow") ||
      selected->thread() != qApp->thread()) return nullptr;
  unsigned matches = 0;
  for (auto window : QApplication::topLevelWidgets())
    if (window->inherits("ParaViewMainWindow")) ++matches;
  return matches == 1 ? selected : nullptr;
}
class Service final : public QObject {
public:
  Service() : QObject(qApp), Gate([this]() { return nativeBusy(); }, this) {}
  uint32_t nativeBusy() const {
    auto core = pqApplicationCore::instance();
    if (!core || !core->getProgressManager() || !core->getServerManagerModel()) return 2;
    if (core->getProgressManager()->isLocked() || Progress) return 1;
    const auto servers = core->getServerManagerModel()->findItems<pqServer*>();
    if (servers.isEmpty()) return 2; // Lost connection is UNKNOWN, never clean.
    for (auto server : servers) {
      if (!server || !server->session()) return 2;
      if (server->session()->GetPendingProgress()) return 1;
    }
    return 0;
  }
  int ready() const {
    if (!qApp || QThread::currentThread() != qApp->thread()) return CAE_WRONG_THREAD;
    auto core = pqApplicationCore::instance();
    return (core && core->getMainWindowEventManager() && core->getProgressManager() && exactMainWindow())
      ? CAE_OK : CAE_NOT_READY;
  }
  int attach(uint64_t pid, uint64_t window, const QByteArray& session, uint64_t client,
             cae_exit_callback callback, uint64_t* registration) {
    const int available = ready(); if (available != CAE_OK) return available;
    auto main = exactMainWindow();
    if (pid != static_cast<uint64_t>(QCoreApplication::applicationPid()) ||
        window != static_cast<uint64_t>(main->winId())) return CAE_WRONG_OWNER;
    if (Gate.registration()) return CAE_BUSY;
    if (Sequence == std::numeric_limits<uint64_t>::max()) return CAE_NOT_READY;
    // Restore connection order at every attach, after stock behavior constructors.
    auto core = pqApplicationCore::instance();
    QObject::disconnect(Review); QObject::disconnect(ProgressConnection);
    Review = connect(core->getMainWindowEventManager(), &pqMainWindowEventManager::close,
                     &Gate, [this](QCloseEvent* event) { Gate.reviewClose(event); }, Qt::DirectConnection);
    Progress = false;
    ProgressConnection = connect(core->getProgressManager(), &pqProgressManager::enableProgress,
      &Gate, [this](bool enabled) { Progress = enabled; }, Qt::DirectConnection);
    int code = Gate.attach(main, ++Sequence, client, callback);
    if (code == CAE_OK) { Session = session; *registration = Sequence; }
    else { QObject::disconnect(Review); QObject::disconnect(ProgressConnection); }
    return code;
  }
  int detach(uint64_t registration) {
    int code = Gate.detach(registration);
    if (code == CAE_OK) releaseConnections();
    return code;
  }
  void releaseConnections() {
    QObject::disconnect(Review); QObject::disconnect(ProgressConnection);
    Review = {}; ProgressConnection = {};
    Session.clear(); Progress = false;
  }
  void shutdown() { Gate.shutdown(); releaseConnections(); }
  cae::CloseGate Gate;
  QMetaObject::Connection Review, ProgressConnection;
  QByteArray Session;
  uint64_t Sequence = 0;
  bool Progress = false;
};
QPointer<Service> Current;
uint32_t runtimeQtVersion() {
  const auto parts = QString::fromLatin1(qVersion()).split('.');
  if (parts.size() < 3) return 0;
  return (parts[0].toUInt() << 16) | (parts[1].toUInt() << 8) | parts[2].toUInt();
}
int status(cae_exit_status* output, uint32_t size) {
  if (!output || size != sizeof(*output) || output->abi != CAE_EXIT_ABI || output->size != sizeof(*output))
    return CAE_BAD_ABI;
  if (!Current) return CAE_NOT_READY;
  if (QThread::currentThread() != Current->thread()) return CAE_WRONG_THREAD;
  *output = {};
  output->abi = CAE_EXIT_ABI; output->size = sizeof(*output);
  output->pid = static_cast<uint64_t>(QCoreApplication::applicationPid());
  output->ready = Current->ready() == CAE_OK ? 1 : 0;
  output->qt_compiled = QT_VERSION; output->qt_runtime = runtimeQtVersion();
  output->paraview_compiled = 0x060200; // CMake requires EXACT 6.2.0 before compilation.
  output->pointer_bits = sizeof(void*) * 8;
  Current->Gate.status(*output);
  output->observer_count += bool(Current->Review) + bool(Current->ProgressConnection);
  if (!output->installed && output->ready) output->window = static_cast<uint64_t>(exactMainWindow()->winId());
  return CAE_OK;
}
}
void pqCaePostExitStarter::onStartup() {
  if (qApp && QThread::currentThread() == qApp->thread() && !Current) Current = new Service;
}
void pqCaePostExitStarter::onShutdown() {
  if (Current) { Current->shutdown(); delete Current.data(); Current.clear(); }
}
extern "C" {
int32_t CAE_EXIT_CALL cae_post_exit_v1_draft(uint64_t registration, cae_exit_draft* output, uint32_t size) {
  try {
    if (!output || size != sizeof(*output) || output->size != sizeof(*output) || output->abi != CAE_EXIT_ABI)
      return CAE_BAD_ABI;
    if (!Current) return CAE_NOT_READY;
    if (QThread::currentThread() != Current->thread()) return CAE_WRONG_THREAD;
    if (!registration || Current->Gate.registration() != registration) return CAE_WRONG_OWNER;
    auto main = exactMainWindow(); if (!main) return CAE_NOT_READY;
    const auto panels = main->findChildren<pqPropertiesPanel*>();
    if (panels.isEmpty()) return CAE_NOT_READY; // Unknown/custom UI is not a clean Properties panel.
    QList<QWidget*> roots;
    bool pending = false;
    for (auto panel : panels) { roots.push_back(panel); pending = pending || panel->canApply() || panel->canReset(); }
    *output = cae::captureDraft(roots, pending);
    return CAE_OK;
  } catch (...) { return CAE_NOT_READY; }
}
int32_t CAE_EXIT_CALL cae_post_exit_v1_probe(cae_exit_status* output, uint32_t size) {
  try { return status(output, size); } catch (...) { return CAE_NOT_READY; }
}
int32_t CAE_EXIT_CALL cae_post_exit_v1_attach(uint32_t version, uint64_t pid, uint64_t window,
 const char* session, uint32_t bytes, uint64_t client, cae_exit_callback callback, uint64_t* registration) {
  try {
    if (version != CAE_EXIT_ABI) return CAE_BAD_ABI;
    if (!session || !bytes || bytes > 127 || !client || !callback || !registration ||
        std::memchr(session, 0, bytes)) return CAE_BAD_ARGUMENT;
    *registration = 0;
    if (!Current) return CAE_NOT_READY;
    QByteArray raw(session, static_cast<int>(bytes));
    if (QString::fromUtf8(raw).toUtf8() != raw) return CAE_BAD_ARGUMENT;
    return Current->attach(pid, window, raw, client, callback, registration);
  } catch (...) { return CAE_NOT_READY; }
}
int32_t CAE_EXIT_CALL cae_post_exit_v1_detach(uint64_t registration) {
  try { return Current ? Current->detach(registration) : CAE_WRONG_OWNER; }
  catch (...) { return CAE_NOT_READY; }
}
int32_t CAE_EXIT_CALL cae_post_exit_v1_status(uint64_t registration, cae_exit_status* output, uint32_t size) {
  try {
    int code = status(output, size);
    if (code != CAE_OK) return code;
    return registration && output->registration == registration ? CAE_OK : CAE_WRONG_OWNER;
  } catch (...) { return CAE_NOT_READY; }
}
int32_t CAE_EXIT_CALL cae_post_exit_v1_prompt(uint64_t registration) {
  try { return Current ? Current->Gate.prompt(registration) : 3; }
  catch (...) { return 3; } // A function error must not alias 1=save or 2=discard.
}
int32_t CAE_EXIT_CALL cae_post_exit_v1_error(uint64_t registration, const char* utf8, uint32_t bytes) {
  try {
    if (!utf8 || !bytes || bytes > 65536 || std::memchr(utf8, 0, bytes)) return CAE_BAD_ARGUMENT;
    return Current ? Current->Gate.error(registration, QString::fromUtf8(utf8, static_cast<int>(bytes))) : CAE_NOT_READY;
  } catch (...) { return CAE_NOT_READY; }
}
}
