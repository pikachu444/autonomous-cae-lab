/* SPDX-License-Identifier: BSD-3-Clause */
#ifndef CAE_POST_EXIT_ABI_H
#define CAE_POST_EXIT_ABI_H
#include <stdint.h>
#if defined(_WIN32)
# define CAE_EXIT_CALL __cdecl
# if defined(CAE_POST_EXIT_BUILD)
#  define CAE_EXIT_EXPORT __declspec(dllexport)
# else
#  define CAE_EXIT_EXPORT __declspec(dllimport)
# endif
#else
# define CAE_EXIT_CALL
# define CAE_EXIT_EXPORT __attribute__((visibility("default")))
#endif
#ifdef __cplusplus
extern "C" {
#endif
/* All arguments are values/bounded UTF-8/POD. No QObject/VTK pointers cross. */
enum { CAE_EXIT_ABI = 1 };
enum { CAE_ALLOW = 1, CAE_BLOCK = 0, CAE_UNKNOWN = -1 };
enum { CAE_BEGIN = 1, CAE_VALIDATE, CAE_ABORTED, CAE_CLOSED, CAE_DESTROYED, CAE_SHUTDOWN };
enum { CAE_OK = 0, CAE_NOT_READY, CAE_WRONG_THREAD, CAE_WRONG_OWNER,
       CAE_BUSY, CAE_BAD_ABI, CAE_BAD_ARGUMENT };
typedef int32_t (CAE_EXIT_CALL *cae_exit_callback)(
  uint64_t client, uint64_t registration, uint64_t attempt, uint32_t event);
typedef struct cae_exit_status {
  uint32_t abi, size;
  uint64_t pid, window, registration, attempt, client;
  uint32_t ready, installed, in_action, native_busy;
  uint32_t settle_timer, filter_count, qt_compiled, qt_runtime;
  uint32_t paraview_compiled, pointer_bits;
  int32_t last_decision;
  uint32_t observer_count;
} cae_exit_status;
typedef struct cae_exit_draft {
  uint32_t abi, size, unapplied, editors;
  char digest[64]; /* SHA-256 hex, exactly 64 bytes, no trailing NUL */
} cae_exit_draft;
CAE_EXIT_EXPORT int32_t CAE_EXIT_CALL cae_post_exit_v1_draft(
  uint64_t registration, cae_exit_draft*, uint32_t);
CAE_EXIT_EXPORT int32_t CAE_EXIT_CALL cae_post_exit_v1_probe(cae_exit_status*, uint32_t);
CAE_EXIT_EXPORT int32_t CAE_EXIT_CALL cae_post_exit_v1_attach(
  uint32_t abi, uint64_t pid, uint64_t window, const char* session, uint32_t session_size,
  uint64_t client, cae_exit_callback callback, uint64_t* registration);
CAE_EXIT_EXPORT int32_t CAE_EXIT_CALL cae_post_exit_v1_detach(uint64_t registration);
CAE_EXIT_EXPORT int32_t CAE_EXIT_CALL cae_post_exit_v1_status(
  uint64_t registration, cae_exit_status*, uint32_t);
/* prompt returns 1=save, 2=discard, 3=cancel. Error codes are NEVER prompt choices. */
CAE_EXIT_EXPORT int32_t CAE_EXIT_CALL cae_post_exit_v1_prompt(uint64_t registration);
CAE_EXIT_EXPORT int32_t CAE_EXIT_CALL cae_post_exit_v1_error(
  uint64_t registration, const char* utf8, uint32_t bytes);
#ifdef __cplusplus
}
static_assert(sizeof(cae_exit_draft) == 80, "ABI 1 draft layout");
static_assert(sizeof(cae_exit_status) == 96, "ABI 1 requires the documented natural layout");
#endif
#endif
