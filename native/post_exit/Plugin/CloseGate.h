/* SPDX-License-Identifier: BSD-3-Clause */
#pragma once
#include "CloseTransaction.h"
#include "cae_post_exit_abi.h"
#include <QObject>
#include <QPointer>
#include <QTimer>
#include <QVector>
#include <QWidget>
#include <functional>
class QCloseEvent;
namespace cae {
/* No global event filter, keyboard grab, replacement QAction or foreign window. */
class CloseGate final : public QObject {
public:
  explicit CloseGate(std::function<uint32_t()> nativeBusy, QObject* parent = nullptr);
  ~CloseGate() override;
  int attach(QWidget* main, uint64_t registration, uint64_t client, cae_exit_callback callback);
  int detach(uint64_t registration);
  void reviewClose(QCloseEvent* event);
  void shutdown();
  int prompt(uint64_t registration);
  int error(uint64_t registration, const QString& message);
  void status(cae_exit_status& output) const;
  uint64_t registration() const { return Registration; }
  bool actionInProgress() const { return Transaction.active() || DialogOpen; }
protected:
  bool eventFilter(QObject* watched, QEvent* event) override;
private:
  int notify(uint32_t event);
  void abort();
  void settle();
  void clear();
  QPointer<QWidget> Main;
  std::function<uint32_t()> NativeBusy;
  CloseTransaction Transaction;
  QTimer Settle;
  QVector<QMetaObject::Connection> Connections;
  uint64_t Registration = 0, Client = 0, Window = 0;
  cae_exit_callback Callback = nullptr;
  int LoopLevel = 0, LastDecision = CAE_UNKNOWN;
  bool DialogOpen = false, InCloseNotification = false;
};
}
