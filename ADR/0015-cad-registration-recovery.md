# ADR 0015: Prepare native bindings privately and recover Core publication

Date: 2026-10-01. Status: accepted design; source and actual acceptance are
separate gates. Applies to R11–13, R19–21, R25, R43, R45 and R51–52 / P1.2b.

## Problem and actual retained failure

Clean Main74217146bd7152236fbd21e252042198b6db9ecb / pinned fixture
3e48bf6138f495299f45b1af254bfb4aaff307b8 reproduced a native/Core split in
the fresh p1-native-registration-red-20261001-01 store. A real native Width
registration persisted alongside Length, then an injected Core registry write
error left the Core entries and revision1 unchanged. A subsequent Length
experiment correctly refused its stale source before creating an experiment.
All14 baseline experiment files and all211 files in the earlier P1.2a store
remained unchanged. The red receipt SHA256 is
b75560fe29c373cfb5b1511c82259f88c1b63e0af025b80a9fff41fdf108760d.

Independent semantic and retention reviews checked the red case and its
39-file / 8,022,230-byte retained snapshot. Its manifest SHA256 is
f802e397d78bbe7bfb58e5d5a50d600a23c1fc02418105de8bd304e9b7484af8.
This is pre-fix failure reproduction, with recovery NOT_RUN. It is not a
corrected-source native acceptance or an engineering verdict.

The pinned registration checks dimensions, renames the selected constraint,
checks final-solid effect and saves. The owned selector worker then normalizes
the literal parameter key and saves again. Calling live bind and catching an
exception cannot undo a saved native file or survive process interruption.

## Decision and ownership

Adapters prepare native bytes inside the Core transaction's private work
folder. The pinned fixture algorithms, selector/name rules, CAD validation and
export behavior remain reused. The adapter captures source bytes once, stages
a separate editable.FCStd, and inspects it before and after binding in fresh
FreeCAD workers. It checks persisted source hashes, final-object identity,
literal key/name/label/bounds, unchanged previous definitions and unique live
identities. All three preparation workers share one monotonic150-second
budget; exhausted phases refuse before starting another worker and preserve
private request/result/stdout/stderr/runtime evidence. Existing individual
worker150-second and outer bridge180-second limits remain unchanged.

The private adapter result is a generic FileRevision: target, prepared file,
before SHA256 and after SHA256. Core interprets filesystem revisions, never
native CAD syntax. An adapter exposing only live bind is refused by Core.
Existing clients continue to use research IDs and opaque native paths. The
fixture pin, numerical engines, experiment schemas and engineering rules do
not change.

Core records verified before/after images with sizes and hashes. New registry
history files must be absent. Targets cannot escape the store, traverse
symlinks, replace immutable experiments or overwrite transaction controls.
The first journal is completed privately in registration_preparations before
its folder is published under registration_transactions. A failed first write
or early process exit retains private evidence without an unrecoverable public
folder. Publication after that point always has a recoverable journal.

Core prepares the complete journal and pending marker before changing any
live target. It publishes native file, new registry history, then current
registry. It verifies all persisted after hashes before writing COMMITTED.
The pending marker remains a consumer gate even if a completed journal write
raises after its file replacement. Acknowledgement syncs the directory before
the final pending unlink. No fallible filesystem action follows that unlink.
This bounds process interruption and injected I/O failures; power-loss
durability of the final acknowledgement remains unqualified.

Cooperating Lab writers share a cached reentrant store lock. Writers retain
the existing study-lock-then-store-lock order used by campaigns. Pending
transactions block native operations, discovery, registry reads, registration
and new CAD experiments. Immutable old experiment inspection remains readable.

Recovery is exposed as Lab.recover_registration(study_id), CLI parameters
recover and the additive OpenScience parameters_recover(study_id) tool. It
accepts a study ID, never user-supplied recovery paths. It validates all images
and all targets before restoring anything. Each current target must equal its
recorded before or after bytes. Foreign edits, corrupt images and invalid paths
remain preserved and blocked. Recovery restores exact originals, removes only
the matching new history image, retains failed preparations and journals, and
can be repeated after interruption. A second completed recovery is a no-op.
No old experiment, thread, evidence or CAD revision is rewritten.

## Alternatives and compatibility

Live bind plus exception handling misses hard process exits and the two native
saves. FreeCAD backup preferences do not coordinate the Core registry/history
or establish exact original-byte restoration. Replacing the store with a
manifest-pointer architecture would also change GUI/native persistence and
requires a separately qualified migration. The bounded journal preserves the
current native file and Core operation model with explicit recovery.

## Verification and limits

Source tests cover private preparation failure, each live publication,
completed-journal errors before and after replacement, acknowledgement failure,
foreign targets, corrupt images, preexisting history, interrupted rollback,
reserved paths, and real child process exits during initial journal creation
and after live publication. Their PreparedAdapter byte stand-in is explicitly
not native CAD proof. Native stage source tests retain malformed/save/timeout
refusals and unchanged existing native checks separately.

A new clean committed-source native acceptance must use real FCStd files,
private staging, native and Core publication failures, fresh-process recovery,
duplicate-free retry and a predeclared analytical/native/STEP comparison.
Original experiment inventories, raw worker output, staged files, journals,
failure receipts, exact source/pin and independent review must be retained.
Source test success alone leaves this actual P1.2b gate OPEN.

Per-file flush/fsync/replacement is not an atomic three-file filesystem
transaction. Power loss, disk loss, hostile journal modification and a
noncooperating GUI edit between the final hash check and replacement are not
qualified. Detected foreign bytes are never overwritten by recovery. Generic
model-input registration and native-import orphan recovery remain separate
gates; this bounded CAD registration decision does not certify them.

OpenScience remains the research control plane; only the study-scoped recovery
tool is additive. All52 requirements stay active. Six engineering validations
remain UNKNOWN, with NOT_RELEASED and solver NOT_RUN for this CAD acceptance.
