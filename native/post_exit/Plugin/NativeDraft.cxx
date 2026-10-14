/* SPDX-License-Identifier: BSD-3-Clause */
#include "NativeDraft.h"
#include <QWidget>
#include <QLineEdit>
#include <QPlainTextEdit>
#include <QTextEdit>
#include <QComboBox>
#include <QCryptographicHash>
#include <QDataStream>
#include <QIODevice>
#include <QSet>
#include <QByteArray>
#include <cstring>
namespace cae {
cae_exit_draft captureDraft(const QList<QWidget*>& roots, bool pending) {
  cae_exit_draft result{};
  result.abi = CAE_EXIT_ABI; result.size = sizeof(result); result.unapplied = pending ? 1 : 0;
  QByteArray bytes;
  QDataStream stream(&bytes, QIODevice::WriteOnly);
  QSet<QWidget*> seen;
  for (auto root : roots) {
    for (auto widget : root->findChildren<QWidget*>()) {
      if (seen.contains(widget)) continue;
      seen.insert(widget);
      QString text;
      bool editable = false, invalid = false;
      if (auto line = qobject_cast<QLineEdit*>(widget)) {
        editable = !line->isReadOnly(); text = line->text();
        // An intermediate value such as "1e" can exist without editingFinished
        // and without an updated vtkSM unchecked property. Never lose it.
        invalid = editable && line->isModified() && !line->hasAcceptableInput();
      } else if (auto plain = qobject_cast<QPlainTextEdit*>(widget)) {
        editable = !plain->isReadOnly(); text = plain->toPlainText();
      } else if (auto rich = qobject_cast<QTextEdit*>(widget)) {
        editable = !rich->isReadOnly(); text = rich->toPlainText();
      } else if (auto combo = qobject_cast<QComboBox*>(widget)) {
        editable = true; text = combo->currentText();
      }
      if (!editable) continue;
      ++result.editors;
      result.unapplied = result.unapplied || invalid;
      // Internal QObject identity is hashed, not exported as an address. Focus,
      // cursor, window enabled state and screen pixels are intentionally absent.
      stream << quint64(reinterpret_cast<quintptr>(widget)) << widget->objectName()
             << QString::fromLatin1(widget->metaObject()->className()) << text << invalid;
    }
  }
  const auto digest = QCryptographicHash::hash(bytes, QCryptographicHash::Sha256).toHex();
  std::memcpy(result.digest, digest.constData(), sizeof(result.digest));
  return result;
}
}
