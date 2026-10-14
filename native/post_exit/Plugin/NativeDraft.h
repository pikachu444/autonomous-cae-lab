/* SPDX-License-Identifier: BSD-3-Clause */
#pragma once
#include "cae_post_exit_abi.h"
#include <QList>
class QWidget;
namespace cae {
/* Only explicitly supplied Properties panel roots are inspected. No editor is
   modified, validated/fixed up, applied, focused, or exposed across the C ABI. */
cae_exit_draft captureDraft(const QList<QWidget*>& roots, bool pending);
}
