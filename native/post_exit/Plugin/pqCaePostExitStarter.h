/* SPDX-License-Identifier: BSD-3-Clause */
#pragma once
#include <QObject>
class pqCaePostExitStarter : public QObject {
  Q_OBJECT
public:
  explicit pqCaePostExitStarter(QObject* parent = nullptr) : QObject(parent) {}
  void onStartup();
  void onShutdown();
};
