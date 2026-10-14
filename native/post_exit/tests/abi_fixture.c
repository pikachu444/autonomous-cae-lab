/* SPDX-License-Identifier: BSD-3-Clause */
#include "cae_post_exit_abi.h"
#include <stddef.h>
/* Test-only library. This does not pretend to be the ParaView plugin. */
CAE_EXIT_EXPORT uint32_t CAE_EXIT_CALL cae_test_status_size(void) { return sizeof(cae_exit_status); }
CAE_EXIT_EXPORT uint32_t CAE_EXIT_CALL cae_test_last_offset(void) { return offsetof(cae_exit_status, last_decision); }
CAE_EXIT_EXPORT int32_t CAE_EXIT_CALL cae_test_roundtrip(cae_exit_callback callback) {
  if (!callback) return CAE_UNKNOWN;
  return callback(UINT64_C(0x8000000000000001), UINT64_C(0x8000000000000002),
                  UINT64_C(0x8000000000000003), CAE_VALIDATE);
}
